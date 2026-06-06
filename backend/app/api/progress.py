"""콘텐츠 읽음 처리.

PATCH /progress 요청 시 user_read_events에 이력을 INSERT한다.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.content import Content
from app.models.event import UserReadEvent
from app.models.user import User
from app.services.profile_vector import update_from_read_history

router = APIRouter(prefix="/progress", tags=["progress"])


class ProgressUpdate(BaseModel):
    user_id: int
    content_id: int


class ProgressResponse(BaseModel):
    status: str
    read_at: datetime


@router.patch("", response_model=ProgressResponse)
def mark_read(
    payload: ProgressUpdate, db: Session = Depends(get_db)
) -> ProgressResponse:
    # 유효성 검증: 존재하지 않는 user/content면 FK 위반 전에 명확한 404 반환
    if db.query(User.id).filter(User.id == payload.user_id).first() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="user not found"
        )
    if db.query(Content.id).filter(Content.id == payload.content_id).first() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="content not found"
        )

    event = UserReadEvent(user_id=payload.user_id, content_id=payload.content_id)
    db.add(event)
    db.commit()
    db.refresh(event)

    # 읽음 이력 기반 profile_vector 갱신 (HIVE-30)
    update_from_read_history(payload.user_id, db)

    return ProgressResponse(status="ok", read_at=event.read_at)
