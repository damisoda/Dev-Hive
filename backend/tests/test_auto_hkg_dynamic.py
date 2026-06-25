"""HIVE-57: Auto-HKG 동적 흡수임계(_adaptive_dedup_thresholds) 단위 테스트.

고정 0.70 대신 노드별 tau_j = max((1-β)분위(음성분포), floor). DB 없이 가짜 conn으로 검증.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np

from app.graph.auto_hkg import _adaptive_dedup_thresholds


def _conn(rows):
    c = MagicMock()
    c.execute.return_value.fetchall.return_value = rows
    return c


# 대주제 A=[1,0], B=[0,1]. 콘텐츠는 자기 축에 가깝게(라벨=정답 대주제).
_SKELETON = {1: np.array([1.0, 0.0]), 2: np.array([0.0, 1.0])}
_ROWS = [
    SimpleNamespace(node_id=1, text_embedding="[1,0.1]"),
    SimpleNamespace(node_id=1, text_embedding="[1,0.2]"),
    SimpleNamespace(node_id=2, text_embedding="[0.1,1]"),
    SimpleNamespace(node_id=2, text_embedding="[0.2,1]"),
]


def test_floor_clamps_tau():
    # floor를 매우 높게 → 모든 tau가 floor로 clamp(흡수정밀도 하한 보장)
    tau = _adaptive_dedup_thresholds(_conn(_ROWS), _SKELETON, beta=0.05, floor=0.99)
    assert tau and all(abs(t - 0.99) < 1e-9 for t in tau.values())


def test_per_node_from_negative_distribution():
    # floor=0 → 음성분포(반대 축 콘텐츠는 코사인 낮음) 기반으로 노드별 tau 산출
    tau = _adaptive_dedup_thresholds(_conn(_ROWS), _SKELETON, beta=0.05, floor=0.0)
    assert set(tau) == {1, 2}
    # 음성(반대 축) 코사인은 낮으므로 tau도 1.0 미만의 낮은 값
    assert all(0.0 <= t < 0.7 for t in tau.values())


def test_empty_labeled_returns_empty():
    # 라벨된 콘텐츠 없으면 빈 dict(→ 호출부는 고정 임계 폴백)
    tau = _adaptive_dedup_thresholds(_conn([]), _SKELETON, beta=0.05, floor=0.62)
    assert tau == {}
