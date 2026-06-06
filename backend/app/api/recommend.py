"""다음 콘텐츠 추천.

⚠️ 추천 로직은 여기서 구현하지 않는다. HIVE-13(진하 담당)의
`app.recommend.rule_based.recommend_next()`를 호출만 한다.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.recommend.rule_based import recommend_next
from app.services.knowledge_tracing import build_user_state

router = APIRouter(prefix="/recommend", tags=["recommend"])


class UserStateResponse(BaseModel):
    user_id: int
    user_state: str


class Recommendation(BaseModel):
    content_id: int
    title: str
    score: float
    reason: Optional[str] = None


class RecommendResponse(BaseModel):
    recommendations: list[Recommendation]


@router.get("/user-state", response_model=UserStateResponse)
def get_user_state(
    user_id: int,
    db: Session = Depends(get_db),
) -> UserStateResponse:
    """유저 상태를 자연어 텍스트로 반환한다.

    HIVE-22(GraphRAG) 추천 시 LLM 프롬프트 컨텍스트로 주입하기 위해 사용한다.
    """
    state = build_user_state(user_id, db)
    return UserStateResponse(user_id=user_id, user_state=state)


@router.get("", response_model=RecommendResponse)
def recommend(
    user_id: int,
    top_n: int = Query(5, ge=1, le=50),
    db: Session = Depends(get_db),
) -> RecommendResponse:
    result = recommend_next(user_id, top_n, db)
    return RecommendResponse(
        recommendations=[Recommendation(**item) for item in result]
    )
