"""HIVE-43 ingest_items 단위 테스트.

QC→배치태깅→임베딩→건별적재 happy path를 가짜 anthropic/openai 클라이언트와
가짜 엔진/커넥션으로 검증한다(실네트워크·실DB 없음).
"""
from types import SimpleNamespace

import app.tagging.ingest as ingest
from app.tagging.ingest import ingest_items


# ─────────────────────────────────────────────────────────────────────────────
# 가짜 Anthropic Message Batches 클라이언트
# ─────────────────────────────────────────────────────────────────────────────


def _result(idx, tags):
    msg = SimpleNamespace(content=[SimpleNamespace(text=__import__("json").dumps(tags))])
    return SimpleNamespace(
        custom_id=f"item-{idx}",
        result=SimpleNamespace(type="succeeded", message=msg),
    )


class _FakeBatches:
    def __init__(self, tags_by_idx):
        self._tags_by_idx = tags_by_idx
        self.submitted = None

    def create(self, requests):
        self.submitted = requests
        return SimpleNamespace(id="msgbatch_fake")

    def retrieve(self, batch_id):
        counts = SimpleNamespace(processing=0, succeeded=len(self._tags_by_idx),
                                 errored=0, canceled=0, expired=0)
        return SimpleNamespace(processing_status="ended", request_counts=counts)

    def results(self, batch_id):
        return [_result(i, t) for i, t in self._tags_by_idx.items()]


class _FakeAnthropic:
    def __init__(self, tags_by_idx):
        self.beta = SimpleNamespace(messages=SimpleNamespace(batches=_FakeBatches(tags_by_idx)))


class _FakeOpenAI:
    pass


# ─────────────────────────────────────────────────────────────────────────────
# 가짜 엔진/커넥션 — load_content 대신 캡처
# ─────────────────────────────────────────────────────────────────────────────


class _FakeConn:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeEngine:
    def __init__(self):
        self.tx_count = 0

    def begin(self):
        self.tx_count += 1
        return _FakeConn()


def _good_tags(q=0.9):
    return {"quality_score": q, "language": "ko", "difficulty": 2,
            "content_type": "experience", "relevance": {}}


def _item(url, **kw):
    base = {"title": "RAG 파이프라인 구축 경험", "body": "충분한 본문",
            "url": url, "source": "velog", "engagement": {"likes": 10, "comments": 3}}
    base.update(kw)
    return base


def test_ingest_items_happy_path(monkeypatch):
    items = [_item("https://a.com"), _item("https://b.com")]
    tags_by_idx = {0: _good_tags(0.9), 1: _good_tags(0.8)}

    monkeypatch.setattr(ingest, "embed_content", lambda item, client: [0.0] * 1536)

    loaded = []
    synth_seen = []

    def fake_load_content(item, tags, embedding, conn, synthesis=None):
        loaded.append(item["url"])
        synth_seen.append(synthesis)
        return 100 + len(loaded)

    monkeypatch.setattr(ingest, "load_content", fake_load_content)

    engine = _FakeEngine()
    stats = ingest_items(items, _FakeAnthropic(tags_by_idx), _FakeOpenAI(), engine)

    assert stats["inserted"] == 2
    assert stats["skipped_quality"] == 0
    assert stats["skipped_dup"] == 0
    assert stats["tag_failed"] == 0
    assert stats["load_failed"] == 0
    assert loaded == ["https://a.com", "https://b.com"]
    assert engine.tx_count == 2  # 건별 트랜잭션
    # HIVE-49 lazy: 적재 시 가공하지 않는다 → synthesis는 항상 None(추천 확정 시 생성).
    assert synth_seen == [None, None]


def test_ingest_items_skips_low_quality(monkeypatch):
    items = [_item("https://a.com"), _item("https://b.com")]
    tags_by_idx = {0: _good_tags(0.9), 1: _good_tags(0.1)}  # 둘째는 quality 미달

    monkeypatch.setattr(ingest, "embed_content", lambda item, client: [0.0] * 1536)
    monkeypatch.setattr(ingest, "load_content", lambda *a, **k: 101)

    stats = ingest_items(items, _FakeAnthropic(tags_by_idx), _FakeOpenAI(), _FakeEngine())
    assert stats["inserted"] == 1
    assert stats["skipped_quality"] == 1


def test_ingest_items_counts_duplicate(monkeypatch):
    items = [_item("https://a.com")]
    monkeypatch.setattr(ingest, "embed_content", lambda item, client: [0.0] * 1536)
    monkeypatch.setattr(ingest, "load_content", lambda *a, **k: None)  # dup → None

    stats = ingest_items(items, _FakeAnthropic({0: _good_tags()}), _FakeOpenAI(), _FakeEngine())
    assert stats["inserted"] == 0
    assert stats["skipped_dup"] == 1


def test_ingest_items_empty_after_qc(monkeypatch):
    # source not allowed → QC가 전부 컷.
    items = [_item("https://a.com", source="hackernews")]
    stats = ingest_items(items, _FakeAnthropic({}), _FakeOpenAI(), _FakeEngine())
    assert stats["qc_passed"] == 0
    assert stats["inserted"] == 0


def test_ingest_items_limit(monkeypatch):
    items = [_item(f"https://a{i}.com") for i in range(5)]
    monkeypatch.setattr(ingest, "embed_content", lambda item, client: [0.0] * 1536)
    monkeypatch.setattr(ingest, "load_content", lambda *a, **k: 1)
    stats = ingest_items(
        items, _FakeAnthropic({0: _good_tags(), 1: _good_tags()}), _FakeOpenAI(),
        _FakeEngine(), limit=2,
    )
    assert stats["total"] == 2  # limit 후 QC total
    assert stats["inserted"] == 2


def test_wait_for_batch_times_out(monkeypatch):
    """배치가 끝나지 않으면 MAX_WAIT_SECONDS 초과 시 TimeoutError로 무한 폴링을 막는다."""
    import pytest

    class _StuckBatches:
        def retrieve(self, batch_id):
            counts = SimpleNamespace(processing=1, succeeded=0, errored=0, canceled=0, expired=0)
            return SimpleNamespace(processing_status="in_progress", request_counts=counts)

    client = SimpleNamespace(
        beta=SimpleNamespace(messages=SimpleNamespace(batches=_StuckBatches()))
    )
    monkeypatch.setattr(ingest, "MAX_WAIT_SECONDS", -1)  # 첫 폴링 직후 한도 초과
    monkeypatch.setattr(ingest.time, "sleep", lambda s: None)

    with pytest.raises(TimeoutError):
        ingest.wait_for_batch(client, "msgbatch_stuck")
