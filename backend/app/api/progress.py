"""콘텐츠 읽음 처리.

PATCH /progress 요청 시 user_read_events에 이력을 INSERT한다.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.database import get_db
from app.models.content import Content
from app.models.event import UserReadEvent
from app.models.user import User
from app.services.content_topic import top_topic_for_contents
from app.services.influence import update_influence_score
from app.services.leveling import check_and_level_up
from app.services.profile_vector import update_from_read_history

router = APIRouter(prefix="/progress", tags=["progress"])
logger = logging.getLogger(__name__)


class ProgressUpdate(BaseModel):
    content_id: int


class ProgressResponse(BaseModel):
    status: str
    read_at: datetime
    leveled_up: bool = False        # 이번 읽음으로 레벨이 올랐는지 (HIVE-36)
    new_level: Optional[str] = None  # 올랐다면 새 레벨, 아니면 None
    influence_score: Optional[int] = None  # 갱신된 영향력 점수 (HIVE-37)


class ReadHistoryItem(BaseModel):
    content_id: int
    title: str
    url: Optional[str] = None
    difficulty: Optional[str] = None
    content_type: Optional[str] = None
    topic: Optional[str] = None       # 소속 대주제 (학습경로 단계 메타, HIVE-65)
    read_at: datetime


class ReadHistoryResponse(BaseModel):
    user_id: int
    items: list[ReadHistoryItem]


@router.get("", response_model=ReadHistoryResponse)
def list_read_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReadHistoryResponse:
    """유저가 읽은 콘텐츠를 읽은 순(오래된→최근)으로 반환한다 (HIVE-65 학습경로 '완료' 구간).

    같은 글을 여러 번 읽었으면 가장 최근 읽음 시각으로 합쳐 한 번만 나온다.
    """
    rows = db.execute(
        text(
            """
            SELECT c.id, c.title, c.url, c.difficulty, c.content_type,
                   MAX(e.read_at) AS read_at
            FROM user_read_events e
            JOIN content c ON c.id = e.content_id
            WHERE e.user_id = :uid
            GROUP BY c.id, c.title, c.url, c.difficulty, c.content_type
            ORDER BY read_at ASC
            """
        ),
        {"uid": current_user.id},
    ).fetchall()
    topics = top_topic_for_contents([r.id for r in rows], db)
    return ReadHistoryResponse(
        user_id=current_user.id,
        items=[
            ReadHistoryItem(
                content_id=r.id,
                title=r.title,
                url=r.url,
                difficulty=r.difficulty,
                content_type=r.content_type,
                topic=topics.get(r.id),
                read_at=r.read_at,
            )
            for r in rows
        ],
    )


@router.patch("", response_model=ProgressResponse)
def mark_read(
    payload: ProgressUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProgressResponse:
    if db.query(Content.id).filter(Content.id == payload.content_id).first() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="content not found"
        )

    event = UserReadEvent(user_id=current_user.id, content_id=payload.content_id)
    db.add(event)
    db.commit()
    db.refresh(event)

    try:
        update_from_read_history(current_user.id, db)
    except Exception:
        logger.exception("profile_vector 갱신 실패 (user_id=%s)", current_user.id)

    level_up = None
    try:
        level_up = check_and_level_up(current_user.id, db)
    except Exception:
        logger.exception("레벨업 체크 실패 (user_id=%s)", current_user.id)

    influence = None
    try:
        influence = update_influence_score(current_user.id, db)
    except Exception:
        logger.exception("influence_score 갱신 실패 (user_id=%s)", current_user.id)

    return ProgressResponse(
        status="ok",
        read_at=event.read_at,
        leveled_up=level_up is not None,
        new_level=level_up["new_level"] if level_up else None,
        influence_score=influence,
    )
