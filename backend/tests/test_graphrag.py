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
    _NEUTRAL_PATH,
    _difficulty_fit,
    _parse_vec,
    _path_score,
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


# --- HIVE-87: precedes 경로 점수(_path_score) ---


def test_path_score_empty_data_is_neutral():
    # precedes 데이터가 비면(prereq_map={}) 모든 후보가 중립 → 기존 동작 보존
    assert _path_score(7, {}, {1: 1.0}) == _NEUTRAL_PATH


def test_path_score_node_none_is_neutral():
    # 대표 노드 없는 콘텐츠(node_id=None) → 중립
    assert _path_score(None, {2: [(1, 0.85)]}, {1: 1.0}) == _NEUTRAL_PATH


def test_path_score_no_prereq_for_node_is_neutral():
    # 루트 토픽(선행 없음)은 중립 — 데이터는 있으나 이 노드만 타깃이 아님
    assert _path_score(3, {2: [(1, 0.85)]}, {1: 1.0}) == _NEUTRAL_PATH


def test_path_score_prereq_mastered_is_high():
    # 선행(node1)을 완전히 익힘 → 준비됨 → 1.0
    assert _path_score(2, {2: [(1, 0.85)]}, {1: 1.0}) == 1.0


def test_path_score_prereq_unlearned_is_zero_not_neutral():
    # 선행을 전혀 안 익힘 → 0.0(아직 이름). 중립 0.5와 구분되는 음의 신호
    assert _path_score(7, {7: [(1, 0.7)]}, {1: 0.0}) == 0.0


def test_path_score_equal_weight_average():
    # 동일 가중치 두 선행, mastery 1.0/0.0 → 평균 0.5
    pm = {2: [(1, 0.5), (4, 0.5)]}
    assert _path_score(2, pm, {1: 1.0, 4: 0.0}) == 0.5


def test_path_score_weighted_average():
    # 비대칭 가중치: (1, w0.8, m1.0), (4, w0.2, m0.0) → 0.8/1.0 = 0.8
    pm = {2: [(1, 0.8), (4, 0.2)]}
    assert abs(_path_score(2, pm, {1: 1.0, 4: 0.0}) - 0.8) < 1e-9


def test_path_score_missing_prereq_in_mastery_treated_zero():
    # 선행 노드가 mastery dict에 없으면 0.0(미학습)으로 — KeyError 없음
    assert _path_score(2, {2: [(1, 1.0)]}, {}) == 0.0


def test_difficulty_target_level_floor_hive95():
    # HIVE-95: 미학습(온보딩만 ≤0.2) 토픽은 선언 레벨 floor로 올라가 입문편향 해소.
    from app.recommend.graphrag import _difficulty_target, _difficulty_fit
    assert _difficulty_target(0.1, 0.5) == 0.5    # 중급 floor 적용
    assert _difficulty_target(0.0, 0.85) == 0.85  # 고급 floor
    assert _difficulty_target(0.1, 0.1) == 0.1    # 입문
    # 읽음으로 학습한(>0.2) 토픽은 실제 mastery 유지(floor 무시).
    assert _difficulty_target(0.7, 0.85) == 0.7
    assert _difficulty_target(0.3, 0.5) == 0.3
    # 중급 미학습 토픽 → 중급 콘텐츠 적합도 > 입문 콘텐츠(편향 해소 검증).
    m = _difficulty_target(0.1, 0.5)
    assert _difficulty_fit("중급", m) > _difficulty_fit("입문", m)
