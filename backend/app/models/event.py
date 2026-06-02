from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer

from app.models.base import Base


class UserReadEvent(Base):
    """db/schema.sql의 user_read_events 테이블에 대응한다.

    유저가 콘텐츠를 읽었음을 기록하는 이력. PATCH /progress에서 INSERT한다.
    """

    __tablename__ = "user_read_events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    content_id = Column(Integer, ForeignKey("content.id", ondelete="CASCADE"))
    read_at = Column(DateTime(timezone=True), default=datetime.utcnow)
