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
