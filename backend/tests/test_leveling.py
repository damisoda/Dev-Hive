"""HIVE-36 레벨업 판정 단위 테스트.

`check_and_level_up`은 DB·mastery에 의존하므로, estimate_mastery는 monkeypatch로 고정하고
DB는 가짜 커넥션으로 흉내낸다. 핵심 검증:
- 임계값 경계(입문→중급 0.6 / 중급→고급 0.75)
- 대주제(parent_id IS NULL)만 평균 — 하위 노드 0.0이 끼어도 승급 막히지 않음
- 고급(최고)에서는 승급 없음
- 조건부 UPDATE 발행 여부
"""
from types import SimpleNamespace

import app.services.leveling as leveling
from app.services.leveling import check_and_level_up


class _Result:
    def __init__(self, rows, rowcount=0):
        self._rows = rows
        self.rowcount = rowcount

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class _FakeConn:
    """current_level 조회 / 대주제 조회 / UPDATE 캡처를 흉내내는 가짜 커넥션.

    update_rowcount: UPDATE가 적중한 행 수(동시성 패배 시뮬레이션은 0).
    """

    def __init__(self, current_level, top_node_ids, update_rowcount=1):
        self._current_level = current_level
        self._top_node_ids = top_node_ids
        self._update_rowcount = update_rowcount
        self.updates = []  # 캡처한 UPDATE params
        self.committed = False

    def execute(self, clause, params=None):
        sql = str(clause)
        if "SELECT current_level" in sql:
            if self._current_level is None:
                return _Result([])
            return _Result([SimpleNamespace(current_level=self._current_level)])
        if "curriculum_nodes WHERE parent_id IS NULL" in sql:
            return _Result([SimpleNamespace(id=i) for i in self._top_node_ids])
        if sql.strip().startswith("UPDATE users"):
            self.updates.append(params)
            return _Result([], rowcount=self._update_rowcount)
        raise AssertionError(f"예상치 못한 쿼리: {sql}")

    def commit(self):
        self.committed = True


def _patch_mastery(monkeypatch, mastery: dict):
    monkeypatch.setattr(leveling, "estimate_mastery", lambda uid, db: mastery)


def test_below_threshold_no_levelup(monkeypatch):
    # 입문, 대주제 평균 0.5 < 0.6 → 승급 없음
    _patch_mastery(monkeypatch, {1: 0.5, 2: 0.5})
    db = _FakeConn("입문", [1, 2])
    assert check_and_level_up(1, db) is None
    assert db.updates == []


def test_beginner_to_mid_at_threshold(monkeypatch):
    # 입문, 평균 0.6 >= 0.6 → 중급
    _patch_mastery(monkeypatch, {1: 0.6, 2: 0.6})
    db = _FakeConn("입문", [1, 2])
    result = check_and_level_up(1, db)
    assert result == {"new_level": "중급"}
    assert db.updates[0]["lv"] == "중급"
    assert db.updates[0]["cur"] == "입문"  # 조건부 UPDATE
    assert db.committed


def test_mid_to_high_threshold(monkeypatch):
    # 중급, 평균 0.75 >= 0.75 → 고급
    _patch_mastery(monkeypatch, {1: 0.8, 2: 0.7})
    db = _FakeConn("중급", [1, 2])
    assert check_and_level_up(1, db) == {"new_level": "고급"}


def test_mid_below_high_threshold(monkeypatch):
    # 중급, 평균 0.7 < 0.75 → 승급 없음
    _patch_mastery(monkeypatch, {1: 0.7, 2: 0.7})
    db = _FakeConn("중급", [1, 2])
    assert check_and_level_up(1, db) is None


def test_high_is_max_no_levelup(monkeypatch):
    # 고급 → 더 올릴 레벨 없음
    _patch_mastery(monkeypatch, {1: 1.0, 2: 1.0})
    db = _FakeConn("고급", [1, 2])
    assert check_and_level_up(1, db) is None
    assert db.updates == []


def test_subnodes_excluded_from_average(monkeypatch):
    # 대주제(1,2)는 0.7로 0.6 넘지만, 하위노드(99)가 0.0.
    # 전체 평균이면 (0.7+0.7+0.0)/3=0.47 < 0.6 이라 승급 막힘.
    # 대주제만 평균하면 0.7 >= 0.6 → 중급 승급되어야 함.
    _patch_mastery(monkeypatch, {1: 0.7, 2: 0.7, 99: 0.0})
    db = _FakeConn("입문", [1, 2])  # 대주제는 1,2뿐 (99는 하위노드)
    assert check_and_level_up(1, db) == {"new_level": "중급"}


def test_user_not_found(monkeypatch):
    _patch_mastery(monkeypatch, {1: 1.0})
    db = _FakeConn(None, [1])
    assert check_and_level_up(999, db) is None


def test_empty_mastery_no_levelup(monkeypatch):
    _patch_mastery(monkeypatch, {})
    db = _FakeConn("입문", [1, 2])
    assert check_and_level_up(1, db) is None


def test_concurrency_loser_returns_none(monkeypatch):
    # 임계값은 넘었지만 조건부 UPDATE가 0행 적중(다른 요청이 먼저 승급) → 거짓 성공 방지
    _patch_mastery(monkeypatch, {1: 0.9, 2: 0.9})
    db = _FakeConn("입문", [1, 2], update_rowcount=0)
    assert check_and_level_up(1, db) is None


def test_levelup_engaged_topics_only_hive95(monkeypatch):
    # HIVE-95: 일부 대주제만 읽음으로 깊게 학습(>0.2), 나머지는 온보딩/미학습(≤0.2).
    # 전체평균이면 고착되지만, '학습한 대주제'(>0.2) 평균으로 판정해 승급해야 한다.
    _patch_mastery(monkeypatch, {1: 0.9, 2: 0.8, 3: 0.05, 4: 0.0, 5: 0.2})
    db = _FakeConn("입문", {1, 2, 3, 4, 5})
    assert check_and_level_up(1, db) == {"new_level": "중급"}  # engaged {0.9,0.8} avg 0.85≥0.6


def test_levelup_no_engaged_no_promote_hive95(monkeypatch):
    # 온보딩만(≤0.2)·읽음 학습 없음 → 승급 보류.
    _patch_mastery(monkeypatch, {1: 0.2, 2: 0.1, 3: 0.0})
    db = _FakeConn("입문", {1, 2, 3})
    assert check_and_level_up(1, db) is None
