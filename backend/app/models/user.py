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
    # HIVE-100: 로그인 아이디/비밀번호. 신규 가입은 필수, 레거시 계정은 NULL(로그인 불가).
    username = Column(String(50), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=True)
    display_name = Column(String(100), nullable=False)
    persona = Column(String(20), nullable=False, default="개발자")
    onboarding_answers = Column(JSONB, nullable=True)
    current_level = Column(String(10), default="입문")
    influence_score = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
