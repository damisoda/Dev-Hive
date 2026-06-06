"""다음 콘텐츠 추천.

⚠️ 추천 로직은 여기서 구현하지 않는다. HIVE-13(진하 담당)의
`app.recommend.rule_based.recommend_next()`를 호출만 한다.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.recommend.rule_based import recommend_next
from app.services.knowledge_tracing import build_user_state, estimate_mastery

router = APIRouter(prefix="/recommend", tags=["recommend"])


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
    if state == "":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="user not found"
        )
    return UserStateResponse(user_id=user_id, user_state=state)


@router.get("/mastery", response_model=MasteryResponse)
def get_mastery(
    user_id: int,
    db: Session = Depends(get_db),
) -> MasteryResponse:
    """노드별 mastery(0~1)를 반환한다.

    HIVE-22(GraphRAG) 난이도 성분 정렬에 사용하기 위한 알고리즘용 숫자 출력.
    """
    mastery = estimate_mastery(user_id, db)
    if not mastery:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="user not found"
        )
    return MasteryResponse(user_id=user_id, mastery=mastery)


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
