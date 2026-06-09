"""HIVE-37 rule_based 피드백 반영 단위 테스트.

피드백 신호(feedback_signals)는 monkeypatch로 고정하고, rule_based가 그 신호로
추천 쿼리를 올바르게 조립하는지(제외 절·too_hard 감점·want_more 보너스, 파라미터)
가짜 conn으로 캡처해 검증한다.
"""
from types import SimpleNamespace

import app.recommend.rule_based as rb
from app.recommend.rule_based import recommend_next


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class _CaptureConn:
    """user row를 돌려주고, 추천 SELECT의 SQL/params를 캡처하는 가짜 conn."""

    def __init__(self, profile_vector="[0.1,0.2]", level="고급"):
        self._pv = profile_vector
        self._level = level
        self.rec_sql = None
        self.rec_params = None

    def execute(self, clause, params=None):
        sql = str(clause)
        if "SELECT current_level, profile_vector" in sql:
            return _Result([SimpleNamespace(current_level=self._level, profile_vector=self._pv)])
        # 추천 본 쿼리 캡처
        self.rec_sql = sql
        self.rec_params = params or {}
        return _Result([])  # 추천 결과는 빈 리스트(조립만 검증)


def _patch_signals(monkeypatch, *, excluded=None, too_hard=None, wm=None):
    monkeypatch.setattr(rb, "feedback_excluded_ids", lambda uid, db: excluded or set())
    monkeypatch.setattr(rb, "too_hard_difficulties", lambda uid, db: too_hard or set())
    monkeypatch.setattr(rb, "want_more_centroid", lambda uid, db: wm)


def test_no_feedback_no_clauses(monkeypatch):
    _patch_signals(monkeypatch)
    db = _CaptureConn()
    recommend_next(1, 5, db)
    assert "excluded" not in db.rec_params
    assert "too_hard" not in db.rec_params
    assert "wm" not in db.rec_params


def test_excluded_adds_clause_and_param(monkeypatch):
    _patch_signals(monkeypatch, excluded={3, 8})
    db = _CaptureConn()
    recommend_next(1, 5, db)
    assert "<> ALL(:excluded)" in db.rec_sql
    assert set(db.rec_params["excluded"]) == {3, 8}


def test_too_hard_adds_penalty(monkeypatch):
    _patch_signals(monkeypatch, too_hard={"고급"})
    db = _CaptureConn()
    recommend_next(1, 5, db)
    assert ":too_hard" in db.rec_sql
    assert db.rec_params["too_hard"] == ["고급"]


def test_want_more_adds_bonus(monkeypatch):
    _patch_signals(monkeypatch, wm="[0.5,0.5]")
    db = _CaptureConn()
    recommend_next(1, 5, db)
    assert "(:wm)::vector" in db.rec_sql
    assert db.rec_params["wm"] == "[0.5,0.5]"


def test_all_signals_combined(monkeypatch):
    _patch_signals(monkeypatch, excluded={1}, too_hard={"중급"}, wm="[0.1]")
    db = _CaptureConn()
    recommend_next(1, 5, db)
    assert "<> ALL(:excluded)" in db.rec_sql
    assert ":too_hard" in db.rec_sql
    assert "(:wm)::vector" in db.rec_sql


def test_null_profile_still_excludes(monkeypatch):
    # profile_vector NULL 폴백(quality 정렬)에서도 제외는 적용돼야 함
    _patch_signals(monkeypatch, excluded={5})
    db = _CaptureConn(profile_vector=None)
    recommend_next(1, 5, db)
    assert "quality_score DESC" in db.rec_sql   # 폴백 경로 확인
    assert "<> ALL(:excluded)" in db.rec_sql    # 제외도 적용
    assert db.rec_params["excluded"] == [5]


def test_null_profile_ignores_wm_too_hard(monkeypatch):
    # 폴백 경로(profile_vector NULL)엔 want_more 보너스/too_hard 감점이 없음(설계: 제외만)
    _patch_signals(monkeypatch, too_hard={"고급"}, wm="[0.1]")
    db = _CaptureConn(profile_vector=None)
    recommend_next(1, 5, db)
    assert "(:wm)::vector" not in db.rec_sql
