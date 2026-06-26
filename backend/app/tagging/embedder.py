"""OpenAI text-embedding-3-small 임베딩 생성 모듈.

토큰 절단(8191 상한)과 재시도(최대 3회)로 장문 콘텐츠 유실을 방지한다(HIVE-84).
"""
from __future__ import annotations

import logging
import time

import tiktoken
from openai import APIStatusError, OpenAI, RateLimitError

logger = logging.getLogger(__name__)

EMBED_MODEL = "text-embedding-3-small"
_ENCODING = "cl100k_base"   # text-embedding-3-small 토크나이저
MAX_TOKENS = 8191            # 모델 컨텍스트 상한
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0     # 초 — 지수 백오프 기반 (1s, 2s, 4s)

_enc: tiktoken.Encoding | None = None


def _get_enc() -> tiktoken.Encoding:
    global _enc
    if _enc is None:
        _enc = tiktoken.get_encoding(_ENCODING)
    return _enc


def _truncate(text: str) -> str:
    """MAX_TOKENS 초과 시 절단하고 경고를 남긴다."""
    enc = _get_enc()
    tokens = enc.encode(text)
    if len(tokens) <= MAX_TOKENS:
        return text
    truncated = enc.decode(tokens[:MAX_TOKENS])
    logger.warning(
        "임베딩 입력 절단: %d → %d 토큰 (원문 %d자)",
        len(tokens), MAX_TOKENS, len(text),
    )
    return truncated


def embed_content(item: dict, client: OpenAI) -> list[float]:
    """title + body를 이어붙여 임베딩을 생성한다.

    8191 토큰 초과 시 절단해 유실을 방지하고,
    RateLimit·서버 오류(5xx)는 최대 3회 지수 백오프 재시도한다.
    클라이언트 오류(4xx)는 즉시 raise한다.
    """
    text_input = _truncate(f"{item.get('title', '')}\n\n{item.get('body', '')}")

    last_exc: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = client.embeddings.create(model=EMBED_MODEL, input=text_input)
            return response.data[0].embedding
        except RateLimitError as e:
            last_exc = e
            wait = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
            logger.warning(
                "임베딩 RateLimitError (시도 %d/%d) — %.1fs 후 재시도",
                attempt, _MAX_RETRIES, wait,
            )
            time.sleep(wait)
        except APIStatusError as e:
            if e.status_code >= 500:
                last_exc = e
                wait = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "임베딩 서버 오류 %d (시도 %d/%d) — %.1fs 후 재시도",
                    e.status_code, attempt, _MAX_RETRIES, wait,
                )
                time.sleep(wait)
            else:
                logger.error("임베딩 API 오류 %d — 재시도 없음: %s", e.status_code, e)
                raise

    logger.error("임베딩 실패 — %d회 재시도 후 포기: %s", _MAX_RETRIES, last_exc)
    assert last_exc is not None
    raise last_exc
