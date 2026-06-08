"""룰베이스 추천 로직 (폴백).

선정 기준:
1. 미독 필터 — user_read_events에 없는 콘텐츠만
2. 피드백 제외 — understood / not_interested 피드백 콘텐츠 제외 (HIVE-37)
3. 난이도 필터 — 유저 current_level 이하만 (입문 ≤ 중급 ≤ 고급)
4. 점수 = 벡터 유사도 + want_more 보너스 − too_hard 난이도 감점 (HIVE-37)
5. profile_vector가 NULL이면 quality_score 내림차순으로 폴백

GraphRAG(메인) 실패 시 호출되는 폴백. 피드백 반영은 여기 우선 구현하고,
공용 제외 헬퍼(feedback_signals)는 GraphRAG도 공유 가능.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.constants import (
    FEEDBACK_TOO_HARD_PENALTY as _W_TOO_HARD,
)
from app.services.constants import (
    FEEDBACK_WANT_MORE_WEIGHT as _W_WANT_MORE,
)
from app.services.feedback_signals import (
    feedback_excluded_ids,
    too_hard_difficulties,
    want_more_centroid,
)

_ALLOWED_LEVELS = {
    "입문": ["입문"],
    "중급": ["입문", "중급"],
    "고급": ["입문", "중급", "고급"],
}


def recommend_next(user_id: int, top_n: int, db: Session) -> list[dict]:
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

    # 피드백 신호 (현재 상태 기반)
    excluded = feedback_excluded_ids(user_id, db)
    too_hard = too_hard_difficulties(user_id, db)
    wm_vec = want_more_centroid(user_id, db)

    # 제외 집합 = 이미 읽음 ∪ 피드백 제외
    params: dict = {"uid": user_id, "n": top_n}
    excl_clause = "c.id NOT IN (SELECT content_id FROM user_read_events WHERE user_id = :uid)"
    if excluded:
        params["excluded"] = list(excluded)
        excl_clause += " AND c.id <> ALL(:excluded)"

    # too_hard 난이도 감점 CASE
    if too_hard:
        params["too_hard"] = list(too_hard)
        too_hard_penalty = f"(CASE WHEN c.difficulty = ANY(:too_hard) THEN {_W_TOO_HARD} ELSE 0 END)"
    else:
        too_hard_penalty = "0"

    if profile_vector is not None:
        params["vec"] = str(profile_vector)
        # want_more 보너스: 중심 벡터와의 코사인 유사도 (없으면 0)
        if wm_vec is not None:
            params["wm"] = wm_vec
            wm_bonus = f"{_W_WANT_MORE} * (1 - (c.text_embedding <=> (:wm)::vector))"
        else:
            wm_bonus = "0"

        rows = db.execute(
            text(
                f"""
                SELECT c.id, c.title, c.quality_score,
                       1 - (c.text_embedding <=> (:vec)::vector) AS similarity,
                       (1 - (c.text_embedding <=> (:vec)::vector))
                         + {wm_bonus} - {too_hard_penalty} AS score
                FROM content c
                WHERE c.text_embedding IS NOT NULL
                  AND (c.difficulty IS NULL OR c.difficulty IN ({allowed_sql}))
                  AND {excl_clause}
                ORDER BY score DESC
                LIMIT :n
                """
            ),
            params,
        ).fetchall()
        return [
            {
                "content_id": row.id,
                "title": row.title,
                "score": round(float(row.score), 4),
                "reason": f"유사도 {round(float(row.similarity) * 100, 1)}%",
            }
            for row in rows
        ]
    else:
        # profile_vector 없으면 quality_score 폴백 (피드백 제외만 반영)
        rows = db.execute(
            text(
                f"""
                SELECT c.id, c.title, c.quality_score
                FROM content c
                WHERE (c.difficulty IS NULL OR c.difficulty IN ({allowed_sql}))
                  AND {excl_clause}
                ORDER BY c.quality_score DESC NULLS LAST, c.id DESC
                LIMIT :n
                """
            ),
            params,
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
