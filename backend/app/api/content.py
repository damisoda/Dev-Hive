"""콘텐츠 목록 조회.

text_embedding / graph_embedding은 무겁고 클라이언트에 불필요하므로 응답 스키마에서
제외한다(쿼리 시에도 SELECT하지 않도록 컬럼을 명시 로드한다).
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session, defer

from app.database import get_db
from app.models.content import Content
from app.models.mapping import ContentNodeMapping

router = APIRouter(prefix="/content", tags=["content"])

# node_id 필터링 시 매핑 관련도 임계값
RELEVANCE_THRESHOLD = 0.5


class ContentItem(BaseModel):
    id: int
    title: str
    url: Optional[str] = None
    source: str
    author_name: Optional[str] = None
    language: Optional[str] = None
    difficulty: Optional[str] = None
    quality_score: Optional[float] = None
    content_type: Optional[str] = None
    tags: list = []
    engagement_likes: Optional[int] = None
    engagement_comments: Optional[int] = None
    published_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ContentListResponse(BaseModel):
    items: list[ContentItem]
    total: int


@router.get("", response_model=ContentListResponse)
def list_content(
    source: Optional[str] = None,
    node_id: Optional[int] = None,
    difficulty: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> ContentListResponse:
    # 벡터 컬럼은 무거우므로 SELECT 자체에서 제외(지연 로드)
    query = db.query(Content).options(
        defer(Content.text_embedding), defer(Content.graph_embedding)
    )

    if node_id is not None:
        query = query.join(
            ContentNodeMapping, ContentNodeMapping.content_id == Content.id
        ).filter(
            ContentNodeMapping.node_id == node_id,
            ContentNodeMapping.relevance_score >= RELEVANCE_THRESHOLD,
        )

    if source is not None:
        query = query.filter(Content.source == source)
    if difficulty is not None:
        query = query.filter(Content.difficulty == difficulty)

    total = query.count()
    rows = (
        query.order_by(Content.created_at.desc().nullslast(), Content.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return ContentListResponse(
        items=[ContentItem.model_validate(row) for row in rows],
        total=total,
    )
