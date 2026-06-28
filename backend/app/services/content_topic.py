"""콘텐츠별 대표 대주제 조회 (HIVE-65 학습경로 단계 메타용).

각 콘텐츠는 content_node_mapping으로 1개 이상의 노드에 연결된다. 학습경로 단계에는
'소속 대주제'를 한 개만 보여주므로, relevance가 가장 높은 매핑의 **최상위 대주제**를
고른다(서브토픽이면 parent로 올라가고, 대주제면 자기 자신).
"""
from sqlalchemy import text
from sqlalchemy.orm import Session


def top_topic_for_contents(content_ids: list[int], db: Session) -> dict[int, str]:
    """{content_id: 대주제명}. 매핑 없는 콘텐츠는 결과에서 빠진다."""
    if not content_ids:
        return {}
    rows = db.execute(
        text(
            """
            SELECT DISTINCT ON (cnm.content_id)
                   cnm.content_id AS content_id,
                   COALESCE(p.name, n.name) AS topic
            FROM content_node_mapping cnm
            JOIN curriculum_nodes n ON n.id = cnm.node_id
            LEFT JOIN curriculum_nodes p ON p.id = n.parent_id
            WHERE cnm.content_id = ANY(:ids)
            ORDER BY cnm.content_id, cnm.relevance_score DESC NULLS LAST
            """
        ),
        {"ids": content_ids},
    ).fetchall()
    return {r.content_id: r.topic for r in rows}
