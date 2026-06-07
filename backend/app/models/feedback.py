from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from app.models.base import Base


class UserContentFeedback(Base):
    """db/schema.sql의 user_content_feedback 테이블에 대응한다 (HIVE-37).

    유저가 콘텐츠에 남긴 명시적 피드백. (user_id, content_id)당 1행이며
    최신 피드백으로 덮어쓴다(upsert). 피드백 변경/삭제로 추천 반영이 즉시 복구된다.
    """

    __tablename__ = "user_content_feedback"

    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    content_id = Column(
        Integer, ForeignKey("content.id", ondelete="CASCADE"), primary_key=True
    )
    feedback = Column(String(20), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow)
