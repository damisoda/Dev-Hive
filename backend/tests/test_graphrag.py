"""HIVE-22 GraphRAG 단위 테스트 (DB 비의존 순수 함수).

4성분 가중치 합, 임베딩 파싱, 난이도-mastery 적합도 로직을 검증한다.
DB가 필요한 recommend_next/estimate_mastery는 디버거 라이브 스모크에서 확인.
"""
import numpy as np

from app.recommend.graphrag import (
    W_DIFF,
    W_DIV,
    W_PATH,
    W_REL,
    _difficulty_fit,
    _parse_vec,
    _template_reason,
)


def test_weights_sum_to_one():
    assert abs((W_REL + W_DIFF + W_PATH + W_DIV) - 1.0) < 1e-9


def test_parse_vec_str_and_list_and_none():
    a = _parse_vec("[0.1,0.2,0.3]")
    b = _parse_vec([0.1, 0.2, 0.3])
    assert a.shape == (3,) and np.allclose(a, b)
    assert _parse_vec(None) is None


def test_difficulty_fit_weak_concept_prefers_intro():
    # 약한 개념(mastery 0) → 입문 적합 최고, 고급 최저
    assert _difficulty_fit("입문", 0.0) == 1.0
    assert _difficulty_fit("고급", 0.0) == 0.0


def test_difficulty_fit_strong_concept_prefers_advanced():
    # 강한 개념(mastery 1) → 고급 적합 최고, 입문 최저
    assert _difficulty_fit("고급", 1.0) == 1.0
    assert _difficulty_fit("입문", 1.0) == 0.0


def test_difficulty_fit_mid():
    assert _difficulty_fit("중급", 0.5) == 1.0


def test_difficulty_fit_unknown_difficulty_is_neutral():
    # 미지정 난이도는 0.5로 취급
    assert _difficulty_fit(None, 0.5) == 1.0


def test_template_reason_shows_interest_only_when_real():
    # profile 기반 관련성이 실제 계산된 경우 → 난이도 + 관심 둘 다
    r = _template_reason({"diff": 0.8, "rel": 0.6, "rel_real": True})
    assert "난이도" in r and "관심" in r
    # quality 폴백(rel_real 아님) → 관심 표기 안 함(오표기 방지)
    r2 = _template_reason({"diff": 0.8, "rel": 0.6, "rel_real": False})
    assert "난이도" in r2 and "관심" not in r2
