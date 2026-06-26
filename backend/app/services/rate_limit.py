"""인증 엔드포인트 레이트 리밋 + LLM 비용 가드레일 (HIVE-92, HIVE-101).

인메모리 슬라이딩 윈도우 카운터 기반.
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

    def clear(self, key: str) -> None:
        with self._lock:
            self._windows.pop(key, None)


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


# ── /login per-username 실패 락아웃 (HIVE-101) ─────────────────────────
# _counter(per-IP·LLM용)와 분리해 키 공간을 격리한다.
# 설계 제약: clear_login_failures는 성공 로그인 시 모든 실패를 지우므로,
# 공격자가 피해자의 정상 로그인 타이밍을 이용해 카운터를 리셋받을 수 있다.
# 진정한 해결은 (IP, username) 복합 키이나 단일 노드 위협 모델에서는 현 방식으로 충분하다.
_MAX_LOGIN_FAILURES = 5
_LOGIN_LOCKOUT_SECS = 15 * 60

_failure_counter = _SlidingWindowCounter()


def check_and_record_login_attempt(username: str) -> None:
    """잠금 확인 + 실패 기록을 단일 락 안에서 원자적으로 수행한다 (TOCTOU 방지).

    성공 로그인 시 반드시 clear_login_failures를 호출해 기록을 지워야 한다.
    """
    allowed, retry_after = _failure_counter.check_and_increment(
        username, _MAX_LOGIN_FAILURES, _LOGIN_LOCKOUT_SECS
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too many failed login attempts, try again later",
            headers={"Retry-After": str(retry_after)},
        )


def clear_login_failures(username: str) -> None:
    _failure_counter.clear(username)


def reset_all_for_testing() -> None:
    """테스트 픽스처 전용. 프로덕션에서 호출 금지."""
    with _counter._lock:
        _counter._windows.clear()
    with _failure_counter._lock:
        _failure_counter._windows.clear()
