from sqlalchemy import Column, Float, ForeignKey, Integer

from app.models.base import Base


class ContentNodeMapping(Base):
    """db/schema.sql의 content_node_mapping 테이블에 대응한다.

    콘텐츠 ↔ 커리큘럼 노드 N:N 매핑. GET /content의 node_id 필터링에 사용한다.
    (curriculum_nodes 모델은 HIVE-15 범위 밖이라 추가하지 않음)
    """

    __tablename__ = "content_node_mapping"

    content_id = Column(
        Integer, ForeignKey("content.id", ondelete="CASCADE"), primary_key=True
    )
    node_id = Column(
        Integer, ForeignKey("curriculum_nodes.id", ondelete="CASCADE"), primary_key=True
    )
    relevance_score = Column(Float, nullable=False, default=0.0)
