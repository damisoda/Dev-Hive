"""유저 학습 통계 (HIVE-37) — influence_score / streak / 잔디 히트맵 조회."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.services.influence import compute_streak, read_heatmap

router = APIRouter(prefix="/stats", tags=["stats"])


class StatsResponse(BaseModel):
    user_id: int
    influence_score: int
    streak: int
    heatmap: dict[str, int]  # {YYYY-MM-DD: 읽은 수}


@router.get("", response_model=StatsResponse)
def get_stats(
    user_id: int,
    days: int = Query(365, ge=1, le=730),
    db: Session = Depends(get_db),
) -> StatsResponse:
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    return StatsResponse(
        user_id=user_id,
        influence_score=user.influence_score or 0,
        streak=compute_streak(user_id, db),
        heatmap=read_heatmap(user_id, db, days),
    )
