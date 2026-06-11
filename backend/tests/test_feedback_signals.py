"""HIVE-37 feedback_signals 단위 테스트 (가짜 conn).

피드백 → 추천 신호 변환 3종: 제외 id / want_more 중심 / too_hard 난이도.
"""
from types import SimpleNamespace

import app.services.feedback_signals as fs
from app.services.feedback_signals import (
    feedback_excluded_ids,
    too_hard_difficulties,
    too_hard_topics,
    understood_topics,
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

    def __init__(self, *, excl_rows=None, wm_scalar=None, th_rows=None, topic_rows=None):
        self._excl = excl_rows or []
        self._wm = wm_scalar
        self._th = th_rows or []
        # 대표 토픽 쿼리는 feedback=:fb 파라미터로 too_hard/understood를 구분 → 피드백별 결과 맵
        self._topics = topic_rows or {}

    def execute(self, clause, params=None):
        sql = str(clause)
        if "feedback = ANY(:types)" in sql:
            return _Result(rows=self._excl)
        if "feedback = 'want_more'" in sql:
            return _Result(scalar=self._wm)
        if "feedback = 'too_hard'" in sql:
            return _Result(rows=self._th)
        if "f.feedback = :fb" in sql:  # 대표 토픽(too_hard_topics / understood_topics)
            fb = (params or {}).get("fb")
            return _Result(rows=self._topics.get(fb, []))
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


# ── too_hard_topics / understood_topics (HIVE-48) ────────────────────

def test_too_hard_topics_set():
    db = _Conn(topic_rows={"too_hard": _rows(11, 22, attr="node_id")})
    assert too_hard_topics(1, db) == {11, 22}


def test_understood_topics_set():
    db = _Conn(topic_rows={"understood": _rows(5, 9, attr="node_id")})
    assert understood_topics(1, db) == {5, 9}


def test_topics_filter_none_node_id():
    # 대표 토픽이 없는(매핑 없는) 콘텐츠의 NULL node_id는 제외
    db = _Conn(topic_rows={"too_hard": _rows(3, None, 7, attr="node_id")})
    assert too_hard_topics(1, db) == {3, 7}


def test_topics_empty():
    db = _Conn(topic_rows={})
    assert too_hard_topics(1, db) == set()
    assert understood_topics(1, db) == set()
