"""콘텐츠 목록 조회.

text_embedding / graph_embedding은 무겁고 클라이언트에 불필요하므로 응답 스키마에서
제외한다(쿼리 시에도 SELECT하지 않도록 컬럼을 명시 로드한다).
"""

import logging
from datetime import datetime
from typing import Optional

import anthropic
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, defer

from app.api.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models.content import Content
from app.models.mapping import ContentNodeMapping
from app.models.user import User
from app.services.lazy_synthesis import ensure_synthesis
from app.services.rate_limit import check_rate_limit, log_llm_call
from app.services.upload import UploadError, upload_user_content

router = APIRouter(prefix="/content", tags=["content"])
logger = logging.getLogger(__name__)

# node_id 필터링 시 매핑 관련도 임계값
RELEVANCE_THRESHOLD = 0.5


def _get_client_ip(request: Request) -> str:
    """실제 클라이언트 IP를 반환한다.

    리버스 프록시(nginx/Tailscale) 환경에서 X-Forwarded-For가 없으면
    모든 요청이 프록시 IP로 묶여 하나의 버킷을 공유하므로 헤더를 우선 확인한다.
    """
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _validate_upload_size(title: str, body: str) -> None:
    """요청 크기 초과 시 413을 던진다."""
    if len(title) > settings.upload_max_title_chars:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"제목은 {settings.upload_max_title_chars}자 이하여야 합니다.",
        )
    if len(body) > settings.upload_max_body_chars:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"본문은 {settings.upload_max_body_chars:,}자 이하여야 합니다.",
        )


class ContentItem(BaseModel):
    id: int
    title: str
    url: Optional[str] = None
    source: str
    author_name: Optional[str] = None
    language: Optional[str] = None
    difficulty: Optional[str] = None
    quality_score: Optional[float] = None
    content_type: Optional[str] = None
    tags: list = []
    engagement_likes: Optional[int] = None
    engagement_comments: Optional[int] = None
    published_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    # 요약본 = 캐시된 synthesis.one_liner(있을 때만). 카드 기본 노출용. 미생성이면 null.
    summary: Optional[str] = None
    # 제목 한글 번역 = 캐시된 synthesis.title_ko (HIVE-66). 영문 제목 '번역 보기' 토글용. 미생성이면 null.
    title_ko: Optional[str] = None

    class Config:
        from_attributes = True


class ContentListResponse(BaseModel):
    items: list[ContentItem]
    total: int


@router.get("", response_model=ContentListResponse)
def list_content(
    source: Optional[str] = None,
    node_id: Optional[int] = None,
    difficulty: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> ContentListResponse:
    # 벡터 컬럼은 무거우므로 SELECT 자체에서 제외(지연 로드)
    query = db.query(Content).options(
        defer(Content.text_embedding), defer(Content.graph_embedding)
    )

    if node_id is not None:
        query = query.join(
            ContentNodeMapping, ContentNodeMapping.content_id == Content.id
        ).filter(
            ContentNodeMapping.node_id == node_id,
            ContentNodeMapping.relevance_score >= RELEVANCE_THRESHOLD,
        )

    if source is not None:
        query = query.filter(Content.source == source)
    if difficulty is not None:
        query = query.filter(Content.difficulty == difficulty)

    total = query.count()
    rows = (
        query.order_by(Content.created_at.desc().nullslast(), Content.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return ContentListResponse(
        items=[ContentItem.model_validate(row) for row in rows],
        total=total,
    )


class ContentUpload(BaseModel):
    title: str
    body: str
    url: Optional[str] = None


class UploadResult(BaseModel):
    content_id: int
    title: str
    action: str                      # existing / new_sub / new_top / skipped
    node_id: Optional[int] = None
    node_name: Optional[str] = None
    is_new_node: bool
    difficulty: Optional[str] = None
    content_type: Optional[str] = None


@router.post("", response_model=UploadResult, status_code=status.HTTP_201_CREATED)
def upload_content(
    payload: ContentUpload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UploadResult:
    """HIVE-33: 사용자 글 업로드 → 태깅·임베딩·적재·Auto-HKG 편입.

    올린 글이 기존 노드에 편입되거나 Auto-HKG가 새 하위/최상위 노드를 생성한다.
    """
    # 요청 크기 검증 (HTTP 컨텍스트 밖에서도 안전하게 호출 가능한 독립 함수)
    _validate_upload_size(payload.title, payload.body)

    # 유저별 레이트리밋 — 실패 시도도 카운트한다(엔드포인트 DoS 방어 목적)
    uid = current_user.id
    check_rate_limit(
        f"upload:min:{uid}",
        settings.upload_rate_per_minute,
        60,
        f"업로드는 분당 {settings.upload_rate_per_minute}회까지 가능합니다. 잠시 후 다시 시도해주세요.",
    )
    check_rate_limit(
        f"upload:day:{uid}",
        settings.upload_rate_per_day,
        86_400,
        f"오늘 업로드 한도({settings.upload_rate_per_day}회)에 도달했습니다. 내일 다시 시도해주세요.",
    )

    try:
        result = upload_user_content(
            payload.title, payload.body, payload.url, current_user.id, db
        )
    except UploadError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except Exception:
        # 태깅/임베딩/Auto-HKG의 upstream(LLM·임베딩 API) 오류 → 사용자 탓 아님(503)
        logger.exception("업로드 처리 실패(upstream)")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="업로드 처리 중 오류가 발생했어요. 잠시 후 다시 시도해주세요.",
        )

    # 실제 LLM 호출이 완료된 뒤 로깅 (실패 시 허위 비용 기록 방지)
    approx_tokens = (len(payload.title) + len(payload.body)) // 4
    log_llm_call("upload/tag", uid, "claude-haiku", approx_tokens)
    log_llm_call("upload/embed", uid, "text-embedding-3-small", approx_tokens)

    return UploadResult(**result)


class SynthesisResponse(BaseModel):
    content_id: int
    content_type: Optional[str] = None
    synthesis: Optional[dict] = None     # {one_liner, key_takeaways[], ...타입별 바디}


@router.get("/{content_id}/synthesis", response_model=SynthesisResponse)
def get_synthesis(
    content_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> SynthesisResponse:
    """재가공본(synthesis) 조회 — '읽기' 시 노출. 캐시 우선(ensure_synthesis):
    DB에 있으면 그대로 반환(Haiku 호출 없음), 없으면 1회 생성·저장. 키 없으면 null(graceful).
    """
    # IP 기반 레이트리밋. X-Forwarded-For 우선 확인(리버스 프록시 환경 대응)
    client_ip = _get_client_ip(request)
    check_rate_limit(
        f"synthesis:min:{client_ip}",
        settings.synthesis_rate_per_minute,
        60,
        f"synthesis 조회는 분당 {settings.synthesis_rate_per_minute}회까지 가능합니다.",
    )

    row = (
        db.query(Content.id, Content.content_type)
        .filter(Content.id == content_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="콘텐츠를 찾을 수 없습니다.")

    key = settings.anthropic_api_key
    client = anthropic.Anthropic(api_key=key) if key else None
    card = ensure_synthesis(content_id, db, client)
    return SynthesisResponse(content_id=content_id, content_type=row.content_type, synthesis=card)
