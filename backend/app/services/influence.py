"""influence_score / streak / 잔디 히트맵 계산 (HIVE-37).

influence_score = (읽은수 × 난이도가중 + streak × 0.5 + 기여) × 레벨가중
  - 기여(HIVE-96): 업로드 × W + 내 업로드를 남이 소비한 횟수 × W (소비뿐 아니라 기여 반영)
  - 읽은수: DISTINCT 콘텐츠 기준(중복 읽음 1회), 난이도별 가중 합산
  - streak: 연속 학습일 (날짜 기준, 마지막 읽음이 오늘/어제면 유지)
  - 레벨가중: current_level(HIVE-36)에 따라 활동 점수를 증폭(곱셈)
"""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.constants import (
    INFLUENCE_CONSUMED_UPLOAD_WEIGHT,
    INFLUENCE_DEFAULT_DIFFICULTY_WEIGHT,
    INFLUENCE_DIFFICULTY_WEIGHT,
    INFLUENCE_LEVEL_MULTIPLIER,
    INFLUENCE_STREAK_WEIGHT,
    INFLUENCE_UPLOAD_WEIGHT,
)

# 서비스 기준 타임존. streak/잔디 날짜를 SQL·Python 양쪽에서 이 TZ로 통일한다
# (UTC 날짜와 로컬 date.today()를 섞으면 자정~오전 사이 읽음이 전날로 밀림).
# KST는 DST가 없어 고정 +9 오프셋으로 처리한다 — Windows(tzdata 부재)에서도 동작.
# SQL의 'Asia/Seoul'은 Postgres 자체 tz DB라 무관하며 +9로 동일.
_SERVICE_TZ = "Asia/Seoul"            # SQL용 (Postgres tz 이름)
_SERVICE_TZ_OFFSET = timezone(timedelta(hours=9))  # Python용 (고정 오프셋)


def _today() -> date:
    return datetime.now(_SERVICE_TZ_OFFSET).date()


def _read_dates(user_id: int, db: Session) -> list[date]:
    """유저가 읽은 '날짜'들을 내림차순(최신순) 중복 제거하여 반환한다."""
    rows = db.execute(
        text(
            """
            SELECT DISTINCT (read_at AT TIME ZONE :tz)::date AS d
            FROM user_read_events
            WHERE user_id = :uid
            ORDER BY d DESC
            """
        ),
        {"uid": user_id, "tz": _SERVICE_TZ},
    ).fetchall()
    return [r.d for r in rows]


def compute_streak(user_id: int, db: Session, today: date | None = None) -> int:
    """연속 학습일을 계산한다.

    날짜 기준(하루 여러 개 읽어도 1일). 마지막 읽음이 오늘이거나 어제면 연속 유지,
    그보다 오래되면 0. 거기서부터 하루씩 거슬러 올라가며 연속된 날만 센다.
    """
    dates = _read_dates(user_id, db)
    if not dates:
        return 0

    today = today or _today()
    latest = dates[0]
    # 마지막 읽음이 오늘/어제가 아니면 streak 끊김
    if (today - latest).days > 1:
        return 0

    streak = 1
    prev = latest
    for d in dates[1:]:
        if (prev - d).days == 1:
            streak += 1
            prev = d
        else:
            break
    return streak


def compute_influence_score(user_id: int, db: Session) -> int:
    """influence_score를 계산해 정수로 반환한다 (저장은 호출부)."""
    row = db.execute(
        text("SELECT current_level FROM users WHERE id = :uid"),
        {"uid": user_id},
    ).fetchone()
    if row is None:
        return 0
    level = row.current_level or "입문"

    # 읽은 콘텐츠(DISTINCT)별 난이도 가중 합
    diff_rows = db.execute(
        text(
            """
            SELECT c.difficulty, COUNT(DISTINCT ure.content_id) AS cnt
            FROM user_read_events ure
            JOIN content c ON c.id = ure.content_id
            WHERE ure.user_id = :uid
            GROUP BY c.difficulty
            """
        ),
        {"uid": user_id},
    ).fetchall()
    read_score = sum(
        INFLUENCE_DIFFICULTY_WEIGHT.get(r.difficulty, INFLUENCE_DEFAULT_DIFFICULTY_WEIGHT)
        * r.cnt
        for r in diff_rows
    )

    streak = compute_streak(user_id, db)
    multiplier = INFLUENCE_LEVEL_MULTIPLIER.get(level, 1.0)

    # HIVE-96: 기여항 — 업로드 + 그 글이 '남에게' 소비된 횟수(자가복제 인센티브의 심장).
    contrib = db.execute(
        text(
            """
            SELECT
              (SELECT COUNT(*) FROM content WHERE uploaded_by = :uid) AS uploads,
              (SELECT COUNT(*) FROM user_read_events ure
                 JOIN content c ON c.id = ure.content_id
               WHERE c.uploaded_by = :uid AND ure.user_id <> :uid) AS consumed
            """
        ),
        {"uid": user_id},
    ).fetchone()
    contribution = (
        (contrib.uploads or 0) * INFLUENCE_UPLOAD_WEIGHT
        + (contrib.consumed or 0) * INFLUENCE_CONSUMED_UPLOAD_WEIGHT
    )

    raw = (read_score + streak * INFLUENCE_STREAK_WEIGHT + contribution) * multiplier
    return round(raw)


def update_influence_score(user_id: int, db: Session) -> int:
    """influence_score를 계산해 users 테이블에 저장하고 값을 반환한다."""
    score = compute_influence_score(user_id, db)
    db.execute(
        text("UPDATE users SET influence_score = :s WHERE id = :uid"),
        {"s": score, "uid": user_id},
    )
    db.commit()
    return score


def read_heatmap(user_id: int, db: Session, days: int = 365) -> dict[str, int]:
    """최근 N일간 일별 읽음 수를 {YYYY-MM-DD: count}로 반환한다 (잔디용)."""
    since = _today() - timedelta(days=days - 1)
    rows = db.execute(
        text(
            """
            SELECT (read_at AT TIME ZONE :tz)::date AS d, COUNT(*) AS cnt
            FROM user_read_events
            WHERE user_id = :uid
              AND (read_at AT TIME ZONE :tz)::date >= :since
            GROUP BY d
            ORDER BY d
            """
        ),
        {"uid": user_id, "since": since, "tz": _SERVICE_TZ},
    ).fetchall()
    return {r.d.isoformat(): r.cnt for r in rows}
