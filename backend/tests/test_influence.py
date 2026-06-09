"""HIVE-37 streak/influence 단위 테스트.

compute_streak은 _read_dates(DB)에 의존하므로 monkeypatch로 날짜를 주입해 검증한다.
경계: 오늘/어제 기준 유지, 하루 끊김, 빈 이력, 하루 중복.
"""
from datetime import date

import app.services.influence as influence
from app.services.influence import compute_streak

TODAY = date(2026, 6, 7)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


def _patch_dates(monkeypatch, dates):
    # 내림차순(최신순) 가정 — _read_dates 계약과 동일
    monkeypatch.setattr(influence, "_read_dates", lambda uid, db: dates)


def test_no_reads(monkeypatch):
    _patch_dates(monkeypatch, [])
    assert compute_streak(1, None, today=TODAY) == 0


def test_today_only(monkeypatch):
    _patch_dates(monkeypatch, [date(2026, 6, 7)])
    assert compute_streak(1, None, today=TODAY) == 1


def test_consecutive_until_today(monkeypatch):
    _patch_dates(monkeypatch, [date(2026, 6, 7), date(2026, 6, 6), date(2026, 6, 5)])
    assert compute_streak(1, None, today=TODAY) == 3


def test_last_read_yesterday_keeps_streak(monkeypatch):
    # 오늘 안 읽었어도 어제까지 연속이면 유지
    _patch_dates(monkeypatch, [date(2026, 6, 6), date(2026, 6, 5)])
    assert compute_streak(1, None, today=TODAY) == 2


def test_gap_breaks_streak(monkeypatch):
    # 마지막 읽음이 그제(6/5) → 오늘과 2일 차이 → 끊김
    _patch_dates(monkeypatch, [date(2026, 6, 5), date(2026, 6, 4)])
    assert compute_streak(1, None, today=TODAY) == 0


def test_internal_gap_stops_count(monkeypatch):
    # 오늘·어제 연속이다가 중간에 끊기면 거기까지만
    _patch_dates(
        monkeypatch,
        [date(2026, 6, 7), date(2026, 6, 6), date(2026, 6, 3), date(2026, 6, 2)],
    )
    assert compute_streak(1, None, today=TODAY) == 2


# ── influence_score 공식 ─────────────────────────────────────────────

class _FakeRow:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _FakeInfluenceConn:
    """compute_influence_score용 가짜 conn: 레벨 + 난이도별 읽음수."""

    def __init__(self, level, diff_counts):
        self._level = level
        self._diff_counts = diff_counts  # {difficulty: count}

    def execute(self, clause, params=None):
        sql = str(clause)
        if "current_level" in sql:
            return _Result([_FakeRow(current_level=self._level)])
        if "GROUP BY c.difficulty" in sql:
            return _Result([_FakeRow(difficulty=d, cnt=c) for d, c in self._diff_counts.items()])
        raise AssertionError(f"예상치 못한 쿼리: {sql}")


def _patch_streak(monkeypatch, value):
    monkeypatch.setattr(influence, "compute_streak", lambda uid, db: value)


def test_influence_basic(monkeypatch):
    # 입문 콘텐츠 1건 + streak 1 + 입문(×1.0) = (1*1 + 1*0.5)*1.0 = 1.5 → 2
    _patch_streak(monkeypatch, 1)
    db = _FakeInfluenceConn("입문", {"입문": 1})
    assert influence.compute_influence_score(1, db) == 2


def test_influence_difficulty_weight(monkeypatch):
    # 고급 2건(가중3) + 중급 1건(가중2) + streak 0 + 중급(×1.15)
    # = (2*3 + 1*2 + 0)*1.15 = 8*1.15 = 9.2 → 9
    _patch_streak(monkeypatch, 0)
    db = _FakeInfluenceConn("중급", {"고급": 2, "중급": 1})
    assert influence.compute_influence_score(1, db) == 9


def test_influence_zero_activity(monkeypatch):
    # 활동 0이면 레벨 높아도(고급 ×1.3) 0 — 곱셈 특성(공짜 점수 없음)
    _patch_streak(monkeypatch, 0)
    db = _FakeInfluenceConn("고급", {})
    assert influence.compute_influence_score(1, db) == 0


def test_influence_null_difficulty(monkeypatch):
    # difficulty NULL → 기본 가중 1. 1건 + streak 0 + 입문 = 1*1*1.0 = 1
    _patch_streak(monkeypatch, 0)
    db = _FakeInfluenceConn("입문", {None: 1})
    assert influence.compute_influence_score(1, db) == 1
