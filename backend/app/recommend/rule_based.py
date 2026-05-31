"""Layer 1 룰베이스 추천 로직.

선정 기준:
1. 미독 필터 — user_read_events에 없는 콘텐츠만
2. 난이도 필터 — 유저 current_level 이하만 (입문 ≤ 중급 ≤ 고급)
3. 벡터 유사도 — user.profile_vector와 content.text_embedding 코사인 유사도 내림차순
4. profile_vector가 NULL이면 quality_score 내림차순으로 폴백

GraphRAG 기반 추천은 Layer 2에서 구현 예정.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

<<<<<<< HEAD
# 난이도 순서 정의 (유저 레벨 이하 콘텐츠만 추천)
_LEVEL_ORDER = {"입문": 0, "중급": 1, "고급": 2}
_ALLOWED_LEVELS = {
    "입문": ["입문"],
    "중급": ["입문", "중급"],
    "고급": ["입문", "중급", "고급"],
}


    # 유저 current_level + profile_vector 조회
    user_row = db.execute(
        text("SELECT current_level, profile_vector FROM users WHERE id = :uid"),
        {"uid": user_id},
    ).fetchone()

    if user_row is None:
        return []

    current_level = user_row.current_level or "입문"
    profile_vector = user_row.profile_vector
    allowed = _ALLOWED_LEVELS.get(current_level, ["입문", "중급", "고급"])
    allowed_sql = ", ".join(f"'{lv}'" for lv in allowed)

    if profile_vector is not None:
        # 벡터 유사도 기반 추천 (코사인 거리 오름차순 = 유사도 내림차순)
        rows = db.execute(
            text(
                f"""
                SELECT c.id, c.title, c.quality_score,
                       1 - (c.text_embedding <=> (:vec)::vector) AS similarity
                FROM content c
                WHERE c.text_embedding IS NOT NULL
                  AND (c.difficulty IS NULL OR c.difficulty IN ({allowed_sql}))
                  AND c.id NOT IN (
                      SELECT content_id FROM user_read_events WHERE user_id = :uid
                  )
                ORDER BY c.text_embedding <=> (:vec)::vector ASC
                LIMIT :n
                """
            ),
            {"vec": str(profile_vector), "uid": user_id, "n": top_n},
        ).fetchall()
        return [
            {
                "content_id": row.id,
                "title": row.title,
                "score": round(float(row.similarity), 4),
                "reason": f"유사도 {round(float(row.similarity) * 100, 1)}%",
            }
            for row in rows
        ]
    else:
        # profile_vector 없으면 quality_score 폴백
        rows = db.execute(
            text(
                f"""
                SELECT c.id, c.title, c.quality_score
                FROM content c
                WHERE (c.difficulty IS NULL OR c.difficulty IN ({allowed_sql}))
                  AND c.id NOT IN (
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
=======

def recommend_next(user_id: int, top_n: int, db: Session) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT c.id, c.title, c.quality_score
            FROM content c
            WHERE c.id NOT IN (
                SELECT content_id FROM user_read_events WHERE user_id = :uid
