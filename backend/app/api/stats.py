"""유저 학습 통계 (HIVE-37) — influence_score / streak / 잔디 히트맵 조회."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
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
    days: int = Query(365, ge=1, le=730),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StatsResponse:
    return StatsResponse(
        user_id=current_user.id,
        influence_score=current_user.influence_score or 0,
        streak=compute_streak(current_user.id, db),
        heatmap=read_heatmap(current_user.id, db, days),
    )
