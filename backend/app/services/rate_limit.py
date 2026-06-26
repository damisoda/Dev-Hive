"""HIVE-92: 인메모리 슬라이딩 윈도우 레이트리밋.

단일 프로세스(uvicorn 1 worker) 전용.
멀티 워커 기동 시 각 프로세스가 독립 카운터를 가지므로 실효 한도가 worker수 배가 된다.
운영에서 --workers > 1 이면 Redis 기반으로 교체할 것.
"""
import logging
import math
import threading
import time

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


class _SlidingWindowCounter:
    """스레드 안전 슬라이딩 윈도우 카운터."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._windows: dict[str, list[float]] = {}

    def check_and_increment(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        """(허용여부, Retry-After초). 허용 시 Retry-After=0.

        pop으로 키를 꺼내 pruning한 뒤 비어있으면 재저장하지 않아
        만료된 사용자 키가 dict에 영구 잔존하는 메모리 누수를 방지한다.
        """
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            pruned = [t for t in self._windows.pop(key, []) if t > cutoff]
            if len(pruned) >= limit:
                self._windows[key] = pruned
                # 가장 오래된 항목이 만료될 때까지 남은 시간
                retry_after = max(1, math.ceil(pruned[0] - cutoff))
                return False, retry_after
            pruned.append(now)
            self._windows[key] = pruned
            return True, 0

    def current_count(self, key: str, window_seconds: int) -> int:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            return sum(1 for t in self._windows.get(key, []) if t > cutoff)


_counter = _SlidingWindowCounter()


def check_rate_limit(key: str, limit: int, window_seconds: int, detail: str) -> None:
    """한도 초과 시 HTTP 429를 던진다. Retry-After는 잔여 대기 시간(초)."""
    allowed, retry_after = _counter.check_and_increment(key, limit, window_seconds)
    if not allowed:
        logger.warning("rate limit exceeded: key=%s limit=%d window=%ds", key, limit, window_seconds)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            headers={"Retry-After": str(retry_after)},
        )


def log_llm_call(endpoint: str, user_id: int | None, model: str, approx_tokens: int = 0) -> None:
    """LLM 호출 1건을 비용 모니터링 로그로 기록한다."""
    logger.info(
        "llm_call endpoint=%s user_id=%s model=%s approx_tokens=%d",
        endpoint,
        user_id,
        model,
        approx_tokens,
    )
