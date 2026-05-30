from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.models.base import Base


class Content(Base):
    """db/schema.sql의 content 테이블에 대응한다.

    text_embedding / graph_embedding은 pgvector 컬럼이며, 무겁고 API 응답에
    불필요하므로 Pydantic 스키마에서 제외한다(ORM 모델에는 유지).
    """

    __tablename__ = "content"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    body = Column(Text, nullable=False)
    url = Column(String(2000), unique=True)
    source = Column(String(20), nullable=False)
    author_name = Column(String(200))
    uploaded_by = Column(Integer, ForeignKey("users.id"))
    language = Column(String(5), default="en")
    difficulty = Column(String(10))
    quality_score = Column(Float)
    content_type = Column(String(20))
    tags = Column(JSONB, default=list)
    text_embedding = Column(Vector(1536))
    graph_embedding = Column(Vector(256))
    engagement_likes = Column(Integer, default=0)
    engagement_comments = Column(Integer, default=0)
    published_at = Column(DateTime(timezone=True))
    crawled_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
