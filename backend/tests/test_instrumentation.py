"""HIVE-96 funnel 계측 단위 테스트 — _rates(순수, 0-safe)."""
from app.services.instrumentation import _rates


def test_rates_normal():
    r = _rates(impressions=100, clicks=20, reads_of_impressed=8)
    assert r["ctr"] == 0.2
    assert r["read_through_rate"] == 0.08
    assert r["click_to_read"] == 0.4


def test_rates_zero_safe():
    # 분모 0(노출/클릭 없음)에도 NaN/0div 없이 0.0.
    r = _rates(0, 0, 0)
    assert r == {"ctr": 0.0, "read_through_rate": 0.0, "click_to_read": 0.0}
    assert _rates(10, 0, 0)["ctr"] == 0.0
    assert _rates(0, 5, 0)["read_through_rate"] == 0.0
