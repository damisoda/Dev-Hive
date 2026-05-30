from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB

from app.models.base import Base


class User(Base):
    """db/schema.sql의 users 테이블에 대응한다.

    pgvector 컬럼(profile_vector)은 SQLAlchemy ORM에서 직접 다루지 않고,
    추천 단계에서 raw SQL 또는 별도 어댑터로 조회/적재한다.
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    display_name = Column(String(100), nullable=False)
    persona = Column(String(20), nullable=False, default="개발자")
    onboarding_answers = Column(JSONB, nullable=True)
    current_level = Column(String(10), default="입문")
    influence_score = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
