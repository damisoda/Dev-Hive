"""피드백 → 추천 신호 변환 (HIVE-37).

추천기(rule_based, 향후 GraphRAG)가 공통으로 소비하는 피드백 파생 신호.
현재 상태(user_content_feedback 테이블)를 읽으므로, 피드백 취소/변경 시 즉시 반영된다.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.constants import FEEDBACK_EXCLUDE


def feedback_excluded_ids(user_id: int, db: Session) -> set[int]:
    """추천에서 제외할 콘텐츠 id (understood / not_interested 피드백).

    추천기의 기존 '이미 읽음' 제외에 더해 사용한다. GraphRAG도 동일 헬퍼를 쓰면
    메인/폴백 양쪽에서 일관되게 제외된다.
    """
    if not FEEDBACK_EXCLUDE:
        return set()
    rows = db.execute(
        text(
            "SELECT content_id FROM user_content_feedback "
            "WHERE user_id = :uid AND feedback = ANY(:types)"
        ),
        {"uid": user_id, "types": list(FEEDBACK_EXCLUDE)},
    ).fetchall()
    return {r.content_id for r in rows}


def want_more_centroid(user_id: int, db: Session) -> str | None:
    """'더 보고 싶어요' 콘텐츠 임베딩 평균(pgvector text). 없으면 None.

    profile_vector를 건드리지 않고, 추천 점수 단계에서 이 중심과의 유사도를
    보너스로 더하는 데 쓴다(벡터 오염 방지).
    """
    raw = db.execute(
        text(
            """
            SELECT AVG(c.text_embedding)::text
            FROM user_content_feedback f
            JOIN content c ON c.id = f.content_id
            WHERE f.user_id = :uid AND f.feedback = 'want_more'
              AND c.text_embedding IS NOT NULL
            """
        ),
        {"uid": user_id},
    ).scalar()
    return raw


def _representative_topics(user_id: int, db: Session, feedback: str) -> set[int]:
    """특정 피드백 콘텐츠의 '대표 토픽' node_id 집합 (HIVE-48).

    대표 토픽 = content_node_mapping에서 relevance_score 최고 노드 — graphrag 후보 쿼리의
    node_id 선정 기준(ORDER BY relevance_score DESC LIMIT 1)과 동일하게 맞춘다.
    feedback 값(too_hard/understood)별로 호출한다(피드백 종류는 호출부에서 고정 — 인젝션 무관).
    """
    rows = db.execute(
        text(
            """
            SELECT (
                SELECT m.node_id FROM content_node_mapping m
                WHERE m.content_id = f.content_id
                ORDER BY m.relevance_score DESC LIMIT 1
            ) AS node_id
            FROM user_content_feedback f
            WHERE f.user_id = :uid AND f.feedback = :fb
            """
        ),
        {"uid": user_id, "fb": feedback},
    ).fetchall()
    return {r.node_id for r in rows if r.node_id is not None}


def too_hard_topics(user_id: int, db: Session) -> set[int]:
    """'어려워요' 콘텐츠의 대표 토픽 node_id 집합 (HIVE-48).

    graphrag가 이 토픽들의 mastery를 하향해 더 쉬운 난이도를 추천하도록 쓴다.
    """
    return _representative_topics(user_id, db, "too_hard")


def understood_topics(user_id: int, db: Session) -> set[int]:
    """'이해했어요' 콘텐츠의 대표 토픽 node_id 집합 (HIVE-48).

    graphrag가 이 토픽들의 mastery를 상향해 더 어려운(심화) 난이도를 추천하도록 쓴다.
    (understood 콘텐츠 자체는 feedback_excluded_ids로 추천에서 제외되지만, 토픽 신호는 남긴다.)
    """
    return _representative_topics(user_id, db, "understood")


def too_hard_difficulties(user_id: int, db: Session) -> set[str]:
    """'어려워요' 표시한 콘텐츠들의 난이도 집합. 이 난이도는 추천에서 감점한다."""
    rows = db.execute(
        text(
            """
            SELECT DISTINCT c.difficulty
            FROM user_content_feedback f
            JOIN content c ON c.id = f.content_id
            WHERE f.user_id = :uid AND f.feedback = 'too_hard'
              AND c.difficulty IS NOT NULL
            """
        ),
        {"uid": user_id},
    ).fetchall()
    return {r.difficulty for r in rows}
