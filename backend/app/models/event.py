from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

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


class RecommendEvent(Base):
    """db/schema.sql의 recommend_events — 추천 funnel 계측(HIVE-96).

    event_type: 'impression'(추천 노출) | 'click'(추천 클릭). 읽음은 user_read_events.
    """

    __tablename__ = "recommend_events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    content_id = Column(Integer, ForeignKey("content.id", ondelete="CASCADE"))
    event_type = Column(String(20), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
