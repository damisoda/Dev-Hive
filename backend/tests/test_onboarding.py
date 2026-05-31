"""HIVE-17 온보딩 자가평가 레벨 산정 로직 테스트.

`compute_initial_level`은 DB에 의존하지 않는 순수 함수이므로 단위 테스트로 검증한다.
점수 경계(입문 0~1 / 중급 2~4 / 고급 5~6)와 방어 로직(누락·범위 밖 값)을 다룬다.
"""

import pytest

from app.api.auth import ONBOARDING_QUESTION_KEYS, compute_initial_level


def _answers(*scores: int) -> dict[str, int]:
    """문항 키 순서대로 점수를 매핑한다."""
    return dict(zip(ONBOARDING_QUESTION_KEYS, scores))


@pytest.mark.parametrize(
    "scores, expected",
    [
        ((0, 0, 0), "입문"),  # 합 0
        ((1, 0, 0), "입문"),  # 합 1 (경계)
        ((1, 1, 0), "중급"),  # 합 2 (경계)
        ((2, 2, 0), "중급"),  # 합 4 (경계)
        ((2, 2, 1), "고급"),  # 합 5 (경계)
        ((2, 2, 2), "고급"),  # 합 6 (최대)
    ],
)
def test_level_boundaries(scores, expected):
    assert compute_initial_level(_answers(*scores)) == expected


def test_empty_answers_defaults_to_beginner():
    assert compute_initial_level({}) == "입문"


def test_missing_keys_treated_as_zero():
    # advanced_topics 누락 → 0점으로 간주, 합 2 → 중급
    assert compute_initial_level({"ai_tool_usage": 1, "llm_understanding": 1}) == "중급"


def test_out_of_range_values_are_clamped():
    # 범위 밖 값은 0~2로 보정: 9→2, -3→0, 누락→0, 합 2 → 중급
    assert compute_initial_level({"ai_tool_usage": 9, "llm_understanding": -3}) == "중급"


def test_unknown_keys_are_ignored():
    # 정의되지 않은 키는 합산에서 제외, 합 0 → 입문
    assert compute_initial_level({"unknown": 2, "extra": 2}) == "입문"
