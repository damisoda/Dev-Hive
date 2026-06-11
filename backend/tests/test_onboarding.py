"""온보딩 자가평가 레벨 산정 로직 테스트 (HIVE-17 → HIVE-36 재설계 반영).

`compute_initial_level`은 DB에 의존하지 않는 순수 함수이므로 단위 테스트로 검증한다.
- ai_score 경계(입문 0~1 / 중급 2~4 / 고급 5~6)
- 개발 baseline 시니어 보정 (중급 상단 ai_score==4에서만 → 고급, 입문 구간은 고정)
- 방어 로직(누락·범위 밖 값·미정의 키)
"""

import pytest
from pydantic import ValidationError

from app.api.auth import ProfileCreate, compute_initial_level
from app.services.constants import PERSONA_ONBOARDING

# 개발자 AI 문항 키 (점수 순서대로 매핑하기 위함)
_AI_KEYS = tuple(PERSONA_ONBOARDING["개발자"]["ai_keys"].keys())


def _ai(*scores: int) -> dict[str, int]:
    """AI 문항 점수만 매핑 (개발 baseline 없음 → 시니어 보정 미적용)."""
    return dict(zip(_AI_KEYS, scores))


@pytest.mark.parametrize(
    "scores, expected",
    [
        ((0, 0, 0), "입문"),  # ai 0
        ((1, 0, 0), "입문"),  # ai 1 (경계)
        ((1, 1, 0), "중급"),  # ai 2 (경계)
        ((2, 2, 0), "중급"),  # ai 4 (경계)
        ((2, 2, 1), "고급"),  # ai 5 (경계)
        ((2, 2, 2), "고급"),  # ai 6 (최대)
    ],
)
def test_ai_score_boundaries(scores, expected):
    assert compute_initial_level(_ai(*scores)) == expected


def test_empty_answers_defaults_to_beginner():
    assert compute_initial_level({}) == "입문"


def test_missing_keys_treated_as_zero():
    assert compute_initial_level({"ai_tool_usage": 1, "llm_understanding": 1}) == "중급"


def test_out_of_range_values_are_clamped():
    # 9→2, -3→0, 누락→0, ai 2 → 중급
    assert compute_initial_level({"ai_tool_usage": 9, "llm_understanding": -3}) == "중급"


def test_unknown_keys_are_ignored():
    assert compute_initial_level({"unknown": 2, "extra": 2}) == "입문"


# ── 개발 baseline 시니어 보정 (HIVE-36) ──────────────────────────────

def test_senior_bumps_only_at_mid_top():
    # ai 4(중급 상단) + 시니어(dev_career 3 + prod 2 = baseline 5) → 고급
    answers = {"ai_tool_usage": 2, "llm_understanding": 2, "advanced_topics": 0,
               "dev_career": 3, "prod_experience": 2}
    assert compute_initial_level(answers) == "고급"


def test_non_senior_stays_mid_at_mid_top():
    # ai 4 + 비시니어(baseline 0) → 중급 유지
    answers = {"ai_tool_usage": 2, "llm_understanding": 2, "advanced_topics": 0}
    assert compute_initial_level(answers) == "중급"


def test_senior_does_not_bump_beginner():
    # ai 1(입문 구간) + 시니어 → 입문 고정 (AI 기초 없으면 보정 안 함)
    answers = {"ai_tool_usage": 1, "dev_career": 3, "prod_experience": 2}
    assert compute_initial_level(answers) == "입문"


def test_senior_does_not_bump_mid_lower():
    # ai 3(중급이지만 상단 아님) + 시니어 → 중급 유지 (ai==4에서만 보정)
    answers = {"ai_tool_usage": 2, "llm_understanding": 1, "advanced_topics": 0,
               "dev_career": 3, "prod_experience": 2}
    assert compute_initial_level(answers) == "중급"


def test_dev_career_not_clamped_to_two():
    # dev_career 3점이 2로 깎이지 않아야 시니어(baseline>=4) 판정됨
    # ai 4 + dev_career 3 + prod 1 = baseline 4 → 시니어 → 고급
    answers = {"ai_tool_usage": 2, "llm_understanding": 2, "advanced_topics": 0,
               "dev_career": 3, "prod_experience": 1}
    assert compute_initial_level(answers) == "고급"


def test_senior_boundary_off_by_one():
    # baseline 정확히 senior_min-1(=3)이면 보정 안 됨 → 중급 유지
    answers = {"ai_tool_usage": 2, "llm_understanding": 2, "advanced_topics": 0,
               "dev_career": 3, "prod_experience": 0}  # baseline 3
    assert compute_initial_level(answers) == "중급"


# ── 입력 검증 (HIVE-36 리뷰 반영) ────────────────────────────────────

def test_profile_create_rejects_unknown_persona():
    with pytest.raises(ValidationError):
        ProfileCreate(display_name="x", persona="해커", onboarding_answers={})


def test_profile_create_accepts_known_persona():
    p = ProfileCreate(display_name="x", persona="개발자", onboarding_answers={})
    assert p.persona == "개발자"


def test_profile_create_rejects_out_of_range_score():
    with pytest.raises(ValidationError):
        ProfileCreate(display_name="x", onboarding_answers={"ai_tool_usage": 99})


def test_profile_create_rejects_empty_name():
    with pytest.raises(ValidationError):
        ProfileCreate(display_name="", onboarding_answers={})
