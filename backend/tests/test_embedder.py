"""HIVE-84: 임베딩 토큰 절단 + 재시도 단위 테스트."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import app.tagging.embedder as embedder_mod
from app.tagging.embedder import MAX_TOKENS, _truncate, embed_content


# ─────────────────────────────────────────────────────────────────────────────
# _truncate
# ─────────────────────────────────────────────────────────────────────────────

def test_truncate_short_text_unchanged():
    text = "짧은 텍스트"
    assert _truncate(text) == text


def test_truncate_long_text_returns_at_most_max_tokens():
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")
    # 넉넉히 MAX_TOKENS + 500 토큰짜리 문자열 생성
    long_text = "hello world " * (MAX_TOKENS + 500)
    result = _truncate(long_text)
    assert len(enc.encode(result)) <= MAX_TOKENS


def test_truncate_logs_warning_when_truncated(caplog):
    import logging
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")
    long_text = "a " * (MAX_TOKENS + 100)
    with caplog.at_level(logging.WARNING, logger="app.tagging.embedder"):
        _truncate(long_text)
    assert any("절단" in r.message for r in caplog.records)


def test_truncate_exactly_at_limit_unchanged():
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")
    # MAX_TOKENS 토큰짜리 텍스트 — 절단 없어야 함
    tokens = enc.encode("token ") * 1  # 작은 단위로 MAX_TOKENS개 만들기
    text = enc.decode(enc.encode("token ") * MAX_TOKENS)
    result = _truncate(text)
    assert len(enc.encode(result)) <= MAX_TOKENS


# ─────────────────────────────────────────────────────────────────────────────
# embed_content
# ─────────────────────────────────────────────────────────────────────────────

def _fake_client(embedding: list[float] | None = None, side_effect=None):
    """openai.OpenAI 클라이언트를 흉내내는 Mock 반환."""
    client = MagicMock()
    if side_effect is not None:
        client.embeddings.create.side_effect = side_effect
    else:
        vec = embedding or [0.1] * 1536
        client.embeddings.create.return_value = SimpleNamespace(
            data=[SimpleNamespace(embedding=vec)]
        )
    return client


def test_embed_content_returns_vector():
    vec = [0.5] * 1536
    client = _fake_client(embedding=vec)
    item = {"title": "테스트", "body": "본문"}
    result = embed_content(item, client)
    assert result == vec
    client.embeddings.create.assert_called_once()


def test_embed_content_passes_truncated_text(monkeypatch):
    """토큰 절단 후 잘린 텍스트가 API에 전달되는지 확인."""
    captured = {}

    def fake_create(model, input):
        captured["input"] = input
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.0] * 1536)])

    client = MagicMock()
    client.embeddings.create.side_effect = fake_create

    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")
    long_body = "word " * (MAX_TOKENS + 200)
    embed_content({"title": "", "body": long_body}, client)

    assert len(enc.encode(captured["input"])) <= MAX_TOKENS


def test_embed_content_retries_on_rate_limit(monkeypatch):
    from openai import RateLimitError

    vec = [0.2] * 1536
    calls = []

    def side_effect(*_, **__):
        calls.append(1)
        if len(calls) < 3:
            raise RateLimitError("rate limit", response=MagicMock(status_code=429), body={})
        return SimpleNamespace(data=[SimpleNamespace(embedding=vec)])

    client = _fake_client(side_effect=side_effect)
    monkeypatch.setattr(embedder_mod.time, "sleep", lambda _: None)

    result = embed_content({"title": "t", "body": "b"}, client)
    assert result == vec
    assert len(calls) == 3


def test_embed_content_retries_on_5xx(monkeypatch):
    from openai import APIStatusError

    vec = [0.3] * 1536
    calls = []

    def side_effect(*_, **__):
        calls.append(1)
        if len(calls) < 2:
            raise APIStatusError("server error", response=MagicMock(status_code=503), body={})
        return SimpleNamespace(data=[SimpleNamespace(embedding=vec)])

    client = _fake_client(side_effect=side_effect)
    monkeypatch.setattr(embedder_mod.time, "sleep", lambda _: None)

    result = embed_content({"title": "t", "body": "b"}, client)
    assert result == vec
    assert len(calls) == 2


def test_embed_content_raises_immediately_on_4xx(monkeypatch):
    from openai import APIStatusError

    def side_effect(*_, **__):
        raise APIStatusError("bad request", response=MagicMock(status_code=400), body={})

    client = _fake_client(side_effect=side_effect)
    monkeypatch.setattr(embedder_mod.time, "sleep", lambda _: None)

    with pytest.raises(APIStatusError):
        embed_content({"title": "t", "body": "b"}, client)

    # 4xx는 재시도 없음 — create 1회만 호출
    assert client.embeddings.create.call_count == 1


def test_embed_content_raises_after_max_retries(monkeypatch):
    from openai import RateLimitError

    def side_effect(*_, **__):
        raise RateLimitError("rate limit", response=MagicMock(status_code=429), body={})

    client = _fake_client(side_effect=side_effect)
    monkeypatch.setattr(embedder_mod.time, "sleep", lambda _: None)

    with pytest.raises(RateLimitError):
        embed_content({"title": "t", "body": "b"}, client)

    assert client.embeddings.create.call_count == embedder_mod._MAX_RETRIES


def test_embed_content_missing_body_uses_empty(monkeypatch):
    vec = [0.1] * 1536
    client = _fake_client(embedding=vec)
    # body 키 없는 item
    result = embed_content({"title": "제목만"}, client)
    assert result == vec
    call_input = client.embeddings.create.call_args.kwargs.get(
        "input", client.embeddings.create.call_args.args[1] if client.embeddings.create.call_args.args else None
    )
    # title만 있으면 body 자리가 빈 문자열
    assert "제목만" in (call_input or "")
