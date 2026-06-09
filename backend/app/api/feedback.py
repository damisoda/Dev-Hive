"""콘텐츠 피드백 (HIVE-37).

유저가 콘텐츠에 남기는 명시적 피드백(이해했어요/어려워요/더 보고 싶어요/관심없어요).
(user, content)당 1행 upsert. 변경/삭제로 추천 반영이 즉시 토글된다.
추천 소비는 rule_based가 현재 상태(테이블)를 읽어서 처리한다.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.content import Content
from app.models.user import User
from app.services.constants import FEEDBACK_TYPES

router = APIRouter(prefix="/feedback", tags=["feedback"])


class FeedbackCreate(BaseModel):
    user_id: int
    content_id: int
    feedback: str

    @field_validator("feedback")
    @classmethod
    def _validate_feedback(cls, v: str) -> str:
        if v not in FEEDBACK_TYPES:
            raise ValueError(
                f"invalid feedback: {v!r} (allowed: {sorted(FEEDBACK_TYPES)})"
            )
        return v


class FeedbackDelete(BaseModel):
    user_id: int
    content_id: int


class FeedbackResponse(BaseModel):
    status: str
    feedback: Optional[str] = None


def _ensure_exists(user_id: int, content_id: int, db: Session) -> None:
    if db.query(User.id).filter(User.id == user_id).first() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    if db.query(Content.id).filter(Content.id == content_id).first() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="content not found")


@router.put("", response_model=FeedbackResponse)
def set_feedback(payload: FeedbackCreate, db: Session = Depends(get_db)) -> FeedbackResponse:
    """피드백을 저장하거나 갱신한다 (upsert)."""
    _ensure_exists(payload.user_id, payload.content_id, db)
    db.execute(
        text(
            """
            INSERT INTO user_content_feedback (user_id, content_id, feedback)
            VALUES (:uid, :cid, :fb)
            ON CONFLICT (user_id, content_id)
            DO UPDATE SET feedback = EXCLUDED.feedback, updated_at = NOW()
            """
        ),
        {"uid": payload.user_id, "cid": payload.content_id, "fb": payload.feedback},
    )
    db.commit()
    return FeedbackResponse(status="ok", feedback=payload.feedback)


@router.delete("", response_model=FeedbackResponse)
def clear_feedback(payload: FeedbackDelete, db: Session = Depends(get_db)) -> FeedbackResponse:
    """피드백을 제거한다 (토글 해제 → 추천 반영 복구)."""
    db.execute(
        text(
            "DELETE FROM user_content_feedback "
            "WHERE user_id = :uid AND content_id = :cid"
        ),
        {"uid": payload.user_id, "cid": payload.content_id},
    )
    db.commit()
    return FeedbackResponse(status="ok", feedback=None)


@router.get("")
def list_feedback(user_id: int, db: Session = Depends(get_db)) -> dict[int, str]:
    """유저의 모든 피드백을 {content_id: feedback}로 반환한다 (프론트 현재 상태 표시용)."""
    rows = db.execute(
        text(
            "SELECT content_id, feedback FROM user_content_feedback WHERE user_id = :uid"
        ),
        {"uid": user_id},
    ).fetchall()
    return {r.content_id: r.feedback for r in rows}
