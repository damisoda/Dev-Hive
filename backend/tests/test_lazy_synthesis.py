"""HIVE-49 ensure_synthesis 단위 테스트 (추천 확정 시 lazy 가공 + 캐시)."""
from types import SimpleNamespace

import app.services.lazy_synthesis as ls
from app.services.lazy_synthesis import ensure_synthesis


class _FakeDB:
    """SELECT는 주어진 row, UPDATE는 기록. commit 호출 여부 추적."""

    def __init__(self, row):
        self._row = row
        self.updates = []
        self.committed = False

    def execute(self, stmt, params=None):
        sql = str(stmt)
        if "UPDATE content" in sql:
            self.updates.append(params)
            return SimpleNamespace()
        return SimpleNamespace(fetchone=lambda: self._row)

    def commit(self):
        self.committed = True


def _row(synthesis=None, ct="tutorial"):
    return SimpleNamespace(title="t", body="b", content_type=ct, synthesis=synthesis)


def test_cache_hit_returns_stored_without_synthesizing(monkeypatch):
    called = []
    monkeypatch.setattr(ls, "synthesize", lambda *a, **k: called.append(1) or {"new": 1})
    db = _FakeDB(_row(synthesis={"one_liner": "캐시된 카드"}))
    out = ensure_synthesis(10, db, client=object())
    assert out == {"one_liner": "캐시된 카드"}
    assert called == []           # 캐시 히트 → synthesize 미호출
    assert db.updates == []        # 저장 안 함


def test_no_client_returns_none(monkeypatch):
    monkeypatch.setattr(ls, "synthesize", lambda *a, **k: {"one_liner": "x"})
    db = _FakeDB(_row(synthesis=None))
    assert ensure_synthesis(10, db, client=None) is None   # 키 없음 → 생성 안 함
    assert db.updates == []


def test_lazy_create_synthesizes_and_persists(monkeypatch):
    card = {"content_type": "tutorial", "one_liner": "새로 가공"}
    monkeypatch.setattr(ls, "synthesize", lambda item, tags, client: card)
    db = _FakeDB(_row(synthesis=None))
    out = ensure_synthesis(10, db, client=object())
    assert out == card
    assert len(db.updates) == 1 and db.committed   # content.synthesis에 저장 + commit


def test_synthesize_none_not_persisted(monkeypatch):
    # 미지원 content_type 등으로 synthesize가 None → 저장하지 않고 None 반환.
    monkeypatch.setattr(ls, "synthesize", lambda *a, **k: None)
    db = _FakeDB(_row(synthesis=None, ct="paper"))
    assert ensure_synthesis(10, db, client=object()) is None
    assert db.updates == []


def test_synthesize_exception_graceful(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("haiku down")
    monkeypatch.setattr(ls, "synthesize", boom)
    db = _FakeDB(_row(synthesis=None))
    assert ensure_synthesis(10, db, client=object()) is None   # 예외 → None(추천 비차단)
    assert db.updates == []


def test_missing_content_returns_none(monkeypatch):
    monkeypatch.setattr(ls, "synthesize", lambda *a, **k: {"one_liner": "x"})
    db = _FakeDB(None)   # 콘텐츠 없음
    assert ensure_synthesis(999, db, client=object()) is None
