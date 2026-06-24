"""HIVE-56 precedes 로더 가드 단위 테스트 (DB 없이 select_loadable 검증)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.load_precedes import select_loadable


def test_normal_dag_all_loaded():
    cands = [(1, 2), (1, 4), (4, 2), (1, 7)]
    ins, skip = select_loadable(cands, existing=[])
    assert set(ins) == set(cands)
    assert skip == []


def test_self_reference_rejected():
    ins, skip = select_loadable([(3, 3)], existing=[])
    assert ins == []
    assert skip == [(3, 3, "self")]


def test_duplicate_rejected_idempotent():
    # 이미 존재하는 엣지 + 후보에 같은 게 또 있어도 한 번도 안 들어감
    ins, skip = select_loadable([(1, 2), (1, 2)], existing=[(1, 2)])
    assert ins == []
    assert all(r == "dup" for _, _, r in skip)


def test_cycle_rejected():
    # 기존 2→1 있는데 1→2 추가하면 사이클 → 거부
    ins, skip = select_loadable([(1, 2)], existing=[(2, 1)])
    assert ins == []
    assert skip == [(1, 2, "cycle")]


def test_cycle_within_candidates_rejected():
    # 1→2, 2→3 적재 후 3→1은 사이클
    ins, skip = select_loadable([(1, 2), (2, 3), (3, 1)], existing=[])
    assert set(ins) == {(1, 2), (2, 3)}
    assert (3, 1, "cycle") in skip
