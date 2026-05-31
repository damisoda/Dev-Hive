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

router = APIRouter(prefix="/recommend", tags=["recommend"])


class Recommendation(BaseModel):
    content_id: int
    title: str
    score: float
    reason: Optional[str] = None


class RecommendResponse(BaseModel):
    recommendations: list[Recommendation]


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
