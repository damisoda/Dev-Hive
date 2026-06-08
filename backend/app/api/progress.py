"""콘텐츠 읽음 처리.

PATCH /progress 요청 시 user_read_events에 이력을 INSERT한다.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.content import Content
from app.models.event import UserReadEvent
from app.models.user import User
from app.services.leveling import check_and_level_up
from app.services.profile_vector import update_from_read_history

router = APIRouter(prefix="/progress", tags=["progress"])
logger = logging.getLogger(__name__)


class ProgressUpdate(BaseModel):
    user_id: int
    content_id: int


class ProgressResponse(BaseModel):
    status: str
    read_at: datetime
    leveled_up: bool = False        # 이번 읽음으로 레벨이 올랐는지 (HIVE-36)
    new_level: Optional[str] = None  # 올랐다면 새 레벨, 아니면 None


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

    # 부가 효과(벡터 갱신·레벨업)는 읽음 처리의 성공을 막지 않도록 격리한다.
    # 실패해도 읽음 자체는 이미 커밋됐으므로 200을 반환하고 로깅만 남긴다.
    try:
        # 읽음 이력 기반 profile_vector 갱신 (HIVE-30)
        update_from_read_history(payload.user_id, db)
    except Exception:
        logger.exception("profile_vector 갱신 실패 (user_id=%s)", payload.user_id)

    level_up = None
    try:
        # mastery 기반 레벨업 체크 (HIVE-36)
        level_up = check_and_level_up(payload.user_id, db)
    except Exception:
        logger.exception("레벨업 체크 실패 (user_id=%s)", payload.user_id)

    return ProgressResponse(
        status="ok",
        read_at=event.read_at,
        leveled_up=level_up is not None,
        new_level=level_up["new_level"] if level_up else None,
    )
