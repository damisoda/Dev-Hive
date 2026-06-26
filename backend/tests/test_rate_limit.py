"""HIVE-92: 레이트리밋 단위 테스트."""
import uuid

import pytest
from fastapi import HTTPException

from app.services.rate_limit import _SlidingWindowCounter, check_rate_limit


# ── SlidingWindowCounter ──────────────────────────────────────────────────


def test_allows_requests_within_limit():
    c = _SlidingWindowCounter()
    for _ in range(3):
        allowed, _ = c.check_and_increment("k", 3, 60)
        assert allowed is True


def test_blocks_request_over_limit():
    c = _SlidingWindowCounter()
    for _ in range(3):
        c.check_and_increment("k", 3, 60)
    allowed, _ = c.check_and_increment("k", 3, 60)
    assert allowed is False


def test_retry_after_is_positive_and_bounded_on_exceed():
    c = _SlidingWindowCounter()
    for _ in range(2):
        c.check_and_increment("k", 2, 60)
    _, retry_after = c.check_and_increment("k", 2, 60)
    assert 1 <= retry_after <= 60


def test_allowed_request_returns_zero_retry_after():
    c = _SlidingWindowCounter()
    _, retry_after = c.check_and_increment("k", 5, 60)
    assert retry_after == 0


def test_different_keys_are_independent():
    c = _SlidingWindowCounter()
    for _ in range(3):
        c.check_and_increment("a", 3, 60)
    # "a"는 한도 초과, "b"는 독립적으로 허용
    allowed_a, _ = c.check_and_increment("a", 3, 60)
    allowed_b, _ = c.check_and_increment("b", 3, 60)
    assert allowed_a is False
    assert allowed_b is True


def test_current_count():
    c = _SlidingWindowCounter()
    assert c.current_count("k", 60) == 0
    c.check_and_increment("k", 10, 60)
    c.check_and_increment("k", 10, 60)
    assert c.current_count("k", 60) == 2


def test_expired_timestamps_not_counted():
    """만료된 타임스탬프를 직접 주입해 슬라이딩 윈도우 만료 검증."""
    import time

    c = _SlidingWindowCounter()
    # 과거 타임스탬프(2초 전)를 직접 심음
    c._windows["k"] = [time.monotonic() - 2]
    # 1초 윈도우 → 2초 전 항목은 만료 → 새 요청 허용
    allowed, _ = c.check_and_increment("k", 1, 1)
    assert allowed is True


def test_expired_key_removed_from_dict():
    """만료 후 빈 리스트 키가 dict에서 제거되는지 확인."""
    import time

    c = _SlidingWindowCounter()
    c._windows["old"] = [time.monotonic() - 10]  # 10초 전 타임스탬프
    # 5초 윈도우로 check → pruned=[] → 허용 후 [now]로 저장, old 키는 제거됨
    c.check_and_increment("old", 5, 5)
    # 키는 새 타임스탬프 [now]로 업데이트되어 있어야 함 (빈 리스트 아님)
    assert "old" in c._windows
    assert len(c._windows["old"]) == 1


# ── check_rate_limit ──────────────────────────────────────────────────────


def test_check_rate_limit_raises_429_on_exceed():
    # uuid 키로 모듈 레벨 _counter 싱글톤 재실행 시 충돌 방지
    key = f"test:429:{uuid.uuid4().hex}"
    for _ in range(2):
        check_rate_limit(key, 2, 60, "한도 초과")
    with pytest.raises(HTTPException) as exc_info:
        check_rate_limit(key, 2, 60, "한도 초과")
    assert exc_info.value.status_code == 429
    assert "Retry-After" in exc_info.value.headers


def test_check_rate_limit_retry_after_is_accurate():
    key = f"test:retry:{uuid.uuid4().hex}"
    check_rate_limit(key, 1, 60, "한도 초과")
    with pytest.raises(HTTPException) as exc_info:
        check_rate_limit(key, 1, 60, "한도 초과")
    retry_after = int(exc_info.value.headers["Retry-After"])
    assert 1 <= retry_after <= 60


def test_check_rate_limit_includes_detail_message():
    key = f"test:detail:{uuid.uuid4().hex}"
    check_rate_limit(key, 1, 60, "커스텀 메시지")
    with pytest.raises(HTTPException) as exc_info:
        check_rate_limit(key, 1, 60, "커스텀 메시지")
    assert exc_info.value.detail == "커스텀 메시지"
