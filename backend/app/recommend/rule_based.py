"""Layer 1 룰베이스 추천 로직.

HIVE-13(진하 담당)에서 정식 벡터 유사도 + 미독 + 난이도 필터 버전으로 교체 예정.
현재는 1차 데모 시연을 위한 quality_score 기반 임시 구현이다.

선정 기준:
- 유저가 아직 읽지 않은(user_read_events에 없는) 콘텐츠만
- quality_score 내림차순 정렬 (NULL은 마지막)
- 상위 top_n건 반환
"""

from sqlalchemy import text
from sqlalchemy.orm import Session


def recommend_next(user_id: int, top_n: int, db: Session) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT c.id, c.title, c.quality_score
            FROM content c
            WHERE c.id NOT IN (
                SELECT content_id FROM user_read_events WHERE user_id = :uid
            )
            ORDER BY c.quality_score DESC NULLS LAST, c.id DESC
            LIMIT :n
            """
        ),
        {"uid": user_id, "n": top_n},
    ).fetchall()
    return [
        {
            "content_id": row.id,
            "title": row.title,
            "score": float(row.quality_score) if row.quality_score is not None else 0.0,
            "reason": None,
        }
        for row in rows
    ]
