"""HIVE-37 feedback_signals 단위 테스트 (가짜 conn).

피드백 → 추천 신호 변환 3종: 제외 id / want_more 중심 / too_hard 난이도.
"""
from types import SimpleNamespace

import app.services.feedback_signals as fs
from app.services.feedback_signals import (
    feedback_excluded_ids,
    too_hard_difficulties,
    want_more_centroid,
)


class _Result:
    def __init__(self, rows=None, scalar=None):
        self._rows = rows or []
        self._scalar = scalar

    def fetchall(self):
        return self._rows

    def scalar(self):
        return self._scalar


class _Conn:
    """SQL 종류별로 정해진 결과를 돌려주는 가짜 커넥션."""

    def __init__(self, *, excl_rows=None, wm_scalar=None, th_rows=None):
        self._excl = excl_rows or []
        self._wm = wm_scalar
        self._th = th_rows or []

    def execute(self, clause, params=None):
        sql = str(clause)
        if "feedback = ANY(:types)" in sql:
            return _Result(rows=self._excl)
        if "feedback = 'want_more'" in sql:
            return _Result(scalar=self._wm)
        if "feedback = 'too_hard'" in sql:
            return _Result(rows=self._th)
        raise AssertionError(f"예상치 못한 쿼리: {sql}")


def _rows(*vals, attr):
    return [SimpleNamespace(**{attr: v}) for v in vals]


# ── feedback_excluded_ids ────────────────────────────────────────────

def test_excluded_ids_collects_set():
    db = _Conn(excl_rows=_rows(3, 7, 9, attr="content_id"))
    assert feedback_excluded_ids(1, db) == {3, 7, 9}


def test_excluded_ids_empty():
    db = _Conn(excl_rows=[])
    assert feedback_excluded_ids(1, db) == set()


def test_excluded_ids_no_exclude_types(monkeypatch):
    # FEEDBACK_EXCLUDE가 비면 쿼리 없이 빈 set (방어)
    monkeypatch.setattr(fs, "FEEDBACK_EXCLUDE", frozenset())
    db = _Conn(excl_rows=_rows(3, attr="content_id"))  # 호출되면 안 됨
    assert feedback_excluded_ids(1, db) == set()


# ── want_more_centroid ───────────────────────────────────────────────

def test_want_more_centroid_value():
    db = _Conn(wm_scalar="[0.1,0.2,0.3]")
    assert want_more_centroid(1, db) == "[0.1,0.2,0.3]"


def test_want_more_centroid_none():
    db = _Conn(wm_scalar=None)
    assert want_more_centroid(1, db) is None


# ── too_hard_difficulties ────────────────────────────────────────────

def test_too_hard_difficulties_set():
    db = _Conn(th_rows=_rows("중급", "고급", attr="difficulty"))
    assert too_hard_difficulties(1, db) == {"중급", "고급"}


def test_too_hard_difficulties_empty():
    db = _Conn(th_rows=[])
    assert too_hard_difficulties(1, db) == set()
