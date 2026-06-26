"""다음 콘텐츠 추천.

HIVE-22: GraphRAG(graphrag.recommend_next)로 추천하고, 실패 시 rule_based(v0)로 폴백한다.
"""

import logging
from typing import Optional

import anthropic
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.config import settings
from app.database import SessionLocal, get_db
from app.models.user import User
from app.recommend.graphrag import recommend_next as _graphrag_recommend
from app.recommend.rule_based import recommend_next as _rule_based_recommend
from app.services.content_topic import top_topic_for_contents
from app.services.knowledge_tracing import build_user_state, estimate_mastery
from app.services.instrumentation import log_click, log_impressions
from app.services.lazy_synthesis import ensure_synthesis


def _synthesize_in_background(content_ids: list[int], api_key: str) -> None:
    """추천 응답 후 백그라운드로 가공 생성·캐시(HIVE-49). 독립 세션/클라이언트 사용.

    동기로 하면 top-N LLM 호출이 추천 응답을 수초 블로킹해 프론트 타임아웃을 넘긴다.
    그래서 추천은 캐시된 요약만 즉시 반환하고, 미캐시분은 여기서 만들어 다음 로드에 노출한다.
    """
    client = anthropic.Anthropic(api_key=api_key)
    db = SessionLocal()
    try:
        for cid in content_ids:
            ensure_synthesis(cid, db, client)
    finally:
        db.close()

router = APIRouter(prefix="/recommend", tags=["recommend"])
logger = logging.getLogger(__name__)


class UserStateResponse(BaseModel):
    user_id: int
    user_state: str


class MasteryResponse(BaseModel):
    user_id: int
    mastery: dict[int, float]


class Recommendation(BaseModel):
    content_id: int
    title: str
    score: float
    reason: Optional[str] = None
    # 표시용 메타 + 가공 요약(HIVE-49). url로 원문 열기, summary는 추천 확정 시 lazy 가공된 one_liner.
    url: Optional[str] = None
    difficulty: Optional[str] = None
    content_type: Optional[str] = None
    summary: Optional[str] = None
    topic: Optional[str] = None       # 소속 대주제 (학습경로 단계 메타, HIVE-65)


class RecommendResponse(BaseModel):
    recommendations: list[Recommendation]


@router.get("/user-state", response_model=UserStateResponse)
def get_user_state(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserStateResponse:
    """유저 상태를 자연어 텍스트로 반환한다."""
    state = build_user_state(current_user.id, db)
    return UserStateResponse(user_id=current_user.id, user_state=state)


@router.get("/mastery", response_model=MasteryResponse)
def get_mastery(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MasteryResponse:
    """노드별 mastery(0~1)를 반환한다."""
    mastery = estimate_mastery(current_user.id, db)
    return MasteryResponse(user_id=current_user.id, mastery=mastery)


@router.get("", response_model=RecommendResponse)
def recommend(
    background_tasks: BackgroundTasks,
    top_n: int = Query(5, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecommendResponse:
    # HIVE-22: GraphRAG 우선, 실패 시 rule_based(v0)로 폴백 — 데모 중 500 방지
    try:
        result = _graphrag_recommend(current_user.id, top_n, db)
    except Exception:
        logger.exception("graphrag 추천 실패 → rule_based 폴백")
        result = _rule_based_recommend(current_user.id, top_n, db)

    # HIVE-49: 표시 메타(url/난이도/타입) + 가공 요약. 응답은 **캐시된 가공만** 즉시 반환하고
    # (client=None으로 ensure_synthesis 호출 = 생성 안 함), 미캐시분은 백그라운드에서 생성·캐시한다.
    # 동기 생성은 top-N LLM 호출로 프론트 타임아웃을 넘기므로 다음 로드에 요약이 채워지는 방식.
    ids = [r["content_id"] for r in result]
    background_tasks.add_task(log_impressions, current_user.id, ids)  # HIVE-96 노출 로깅
    meta = {}
    if ids:
        meta = {
            row.id: row
            for row in db.execute(
                text("SELECT id, url, difficulty, content_type FROM content WHERE id = ANY(:ids)"),
                {"ids": ids},
            )
        }
    topics = top_topic_for_contents(ids, db)
    recs: list[Recommendation] = []
    uncached: list[int] = []
    for r in result:
        m = meta.get(r["content_id"])
        card = ensure_synthesis(r["content_id"], db, None)  # 캐시 조회만(생성 X)
        if card is None:
            uncached.append(r["content_id"])
        recs.append(Recommendation(
            content_id=r["content_id"],
            title=r["title"],
            score=r["score"],
            reason=r.get("reason"),
            url=(m.url if m else None),
            difficulty=(m.difficulty if m else None),
            content_type=(m.content_type if m else None),
            summary=(card.get("one_liner") if isinstance(card, dict) else None),
            topic=topics.get(r["content_id"]),
        ))

    # 미캐시 가공은 응답 후 백그라운드로(다음 추천/새로고침 시 요약 노출). 키 있을 때만.
    if uncached and settings.anthropic_api_key:
        background_tasks.add_task(_synthesize_in_background, uncached, settings.anthropic_api_key)

    return RecommendResponse(recommendations=recs)


class RecommendClickRequest(BaseModel):
    content_id: int


@router.post("/click")
def recommend_click(
    payload: RecommendClickRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """추천 클릭 로깅 (HIVE-96 funnel). 프론트가 추천 카드 클릭 시 호출 → CTR 분자."""
    log_click(current_user.id, payload.content_id, db)
    return {"ok": True}
