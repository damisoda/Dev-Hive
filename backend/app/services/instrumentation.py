"""추천 funnel 계측 (HIVE-96) — 노출/클릭 로깅 + CTR/retention 집계.

문제: impression/CTR/funnel/retention 로깅이 0이라 추천 클릭률조차 측정 불가였다.
- log_impressions: /recommend 응답 후 백그라운드로 노출 기록(자체 세션).
- log_click: 추천 클릭 시 기록(요청 세션).
- funnel_metrics: 노출→클릭→읽음 CTR + retention + 북극성(기여 소비 루프 활성 기여자).
읽음(conversion)은 user_read_events 재사용. recommend_events = impression/click 전용.
"""
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal

logger = logging.getLogger(__name__)

_SERVICE_TZ = "Asia/Seoul"


def log_impressions(user_id: int, content_ids: list[int]) -> None:
    """추천 노출 기록(백그라운드용 — 자체 세션). 실패해도 추천 응답엔 영향 없음."""
    ids = [int(c) for c in (content_ids or [])]
    if not ids:
        return
    db = SessionLocal()
    try:
        db.execute(
            text(
                "INSERT INTO recommend_events (user_id, content_id, event_type) "
                "VALUES (:uid, :cid, 'impression')"
            ),
            [{"uid": user_id, "cid": c} for c in ids],
        )
        db.commit()
    except Exception as exc:  # 계측 실패가 사용자 경험을 막지 않게 삼킴
        db.rollback()
        logger.warning("impression 로깅 실패: %s", exc)
    finally:
        db.close()


def log_click(user_id: int, content_id: int, db: Session) -> None:
    """추천 클릭 기록(요청 세션). 클릭마다 1행(멱등 아님 — CTR 분자)."""
    db.execute(
        text(
            "INSERT INTO recommend_events (user_id, content_id, event_type) "
            "VALUES (:uid, :cid, 'click')"
        ),
        {"uid": user_id, "cid": content_id},
    )
    db.commit()


def _rates(impressions: int, clicks: int, reads_of_impressed: int) -> dict:
    """funnel 비율(0-safe). 분모 0이면 0.0."""
    return {
        "ctr": round(clicks / impressions, 4) if impressions else 0.0,
        "read_through_rate": round(reads_of_impressed / impressions, 4) if impressions else 0.0,
        "click_to_read": round(reads_of_impressed / clicks, 4) if clicks else 0.0,
    }


def funnel_metrics(db: Session, days: int = 30) -> dict:
    """추천 funnel(노출→클릭→읽음) + retention + 북극성 집계 (HIVE-96).

    - ctr = 클릭/노출, read_through = 노출된 추천을 실제 읽은 (user,content)/노출.
    - retention = 윈도우 내 2일 이상 학습한 유저 / 1일 이상 학습한 유저.
    - 북극성 = 자가복제 루프 활성도: 내 업로드가 '남에게' 소비된 기여자 수.
    """
    days = int(days)
    p = {"days": days}
    row = db.execute(
        text(
            "SELECT COUNT(*) FILTER (WHERE event_type='impression') AS imp, "
            "COUNT(*) FILTER (WHERE event_type='click') AS clk "
            "FROM recommend_events WHERE created_at >= now() - make_interval(days => :days)"
        ),
        p,
    ).fetchone()
    impressions, clicks = (row.imp or 0), (row.clk or 0)

    reads = db.execute(
        text(
            """
            SELECT COUNT(*) FROM (
              SELECT DISTINCT re.user_id, re.content_id
              FROM recommend_events re
              JOIN user_read_events ure
                ON ure.user_id = re.user_id AND ure.content_id = re.content_id
              WHERE re.event_type='impression'
                AND re.created_at >= now() - make_interval(days => :days)
            ) t
            """
        ),
        p,
    ).scalar() or 0

    ret = db.execute(
        text(
            """
            SELECT COUNT(*) FILTER (WHERE d >= 2) AS returning, COUNT(*) AS active
            FROM (
              SELECT user_id, COUNT(DISTINCT (read_at AT TIME ZONE :tz)::date) AS d
              FROM user_read_events
              WHERE read_at >= now() - make_interval(days => :days)
              GROUP BY user_id
            ) u
            """
        ),
        {**p, "tz": _SERVICE_TZ},
    ).fetchone()
    returning, active = (ret.returning or 0), (ret.active or 0)

    contributors = db.execute(
        text(
            """
            SELECT COUNT(DISTINCT c.uploaded_by)
            FROM content c JOIN user_read_events ure ON ure.content_id = c.id
            WHERE c.uploaded_by IS NOT NULL AND ure.user_id <> c.uploaded_by
              AND ure.read_at >= now() - make_interval(days => :days)
            """
        ),
        p,
    ).scalar() or 0

    return {
        "window_days": days,
        "impressions": impressions,
        "clicks": clicks,
        "reads_of_impressed": reads,
        **_rates(impressions, clicks, reads),
        "active_learners": active,
        "returning_learners": returning,
        "retention_rate": round(returning / active, 4) if active else 0.0,
        "north_star_active_contributors": contributors,
    }
