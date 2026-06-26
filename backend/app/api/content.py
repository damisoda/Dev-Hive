"""콘텐츠 목록 조회.

text_embedding / graph_embedding은 무겁고 클라이언트에 불필요하므로 응답 스키마에서
제외한다(쿼리 시에도 SELECT하지 않도록 컬럼을 명시 로드한다).
"""

import logging
from datetime import datetime
from typing import Optional

import anthropic
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, defer

from app.api.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models.content import Content
from app.models.mapping import ContentNodeMapping
from app.models.user import User
from app.services.lazy_synthesis import ensure_synthesis
from app.services.upload import UploadError, upload_user_content

router = APIRouter(prefix="/content", tags=["content"])
logger = logging.getLogger(__name__)

# node_id 필터링 시 매핑 관련도 임계값
RELEVANCE_THRESHOLD = 0.5


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
        query.order_by(Content.published_at.desc().nullslast(), Content.id.desc())
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
    return UploadResult(**result)


class SynthesisResponse(BaseModel):
    content_id: int
    content_type: Optional[str] = None
    synthesis: Optional[dict] = None     # {one_liner, key_takeaways[], ...타입별 바디}


@router.get("/{content_id}/synthesis", response_model=SynthesisResponse)
def get_synthesis(content_id: int, db: Session = Depends(get_db)) -> SynthesisResponse:
    """재가공본(synthesis) 조회 — '읽기' 시 노출. 캐시 우선(ensure_synthesis):
    DB에 있으면 그대로 반환(Haiku 호출 없음), 없으면 1회 생성·저장. 키 없으면 null(graceful).
    """
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
