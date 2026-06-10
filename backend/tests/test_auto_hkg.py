"""HIVE-44 Auto-HKG 2-패스 단위 테스트.

LLM/DB 없이 가짜 커넥션 + 가짜 Haiku로 2-패스 로직을 검증한다.
- 1패스: 스켈레톤 흡수(top 코사인 >= DEDUP)
- 2패스: 잔여 클러스터링(연결요소), 크기 >= MIN만 노드 승격, 미만은 고아 → 최근접 매핑
- 고아노드 금지(단일 콘텐츠 노드 0), 풀 미오염(새 노드는 흡수 후보가 아님)
- 클러스터 네이밍은 Haiku 호출 1회/클러스터, 실패 시 폴백
"""
import json
from types import SimpleNamespace

import numpy as np

from app.graph.auto_hkg import (
    _cluster_residuals,
    _name_cluster,
    _nearest,
    expand_graph,
)


# ─────────────────────────────────────────────────────────────────────────────
# 가짜 커넥션 — SQL 종류별로 분기해 응답
# ─────────────────────────────────────────────────────────────────────────────


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _Conn:
    """expand_graph가 부르는 SQL을 종류별로 흉내내는 가짜 커넥션.

    skeleton_rows / root_rows / content_rows: SimpleNamespace 목록.
    created: 생성된 (name, desc, parent_id). mappings: (content_id, node_id, score).
    """

    def __init__(self, skeleton_rows, root_rows, content_rows, new_id_start=900):
        self._skeleton = skeleton_rows
        self._roots = root_rows
        self._contents = content_rows
        self._next_id = new_id_start
        self.created = []
        self.mappings = []

    def execute(self, clause, params=None):
        sql = str(clause)
        if "INSERT INTO curriculum_nodes" in sql:
            self.created.append((params["name"], params["desc"], params["parent_id"]))
            nid = self._next_id
            self._next_id += 1
            return _Result([SimpleNamespace(id=nid)])
        if "INSERT INTO content_node_mapping" in sql:
            self.mappings.append((params["cid"], params["nid"], params["score"]))
            return _Result([])
        # SELECT 분기: roots(대주제, parent NULL) → skeleton → contents
        if "parent_id IS NULL" in sql:
            return _Result(self._roots)
        if "SELECT m.node_id" in sql:
            return _Result(self._skeleton)
        if "FROM content c" in sql:
            return _Result(self._contents)
        return _Result([])


class _FakeAnthropic:
    """_name_cluster용 가짜 Haiku. raise_exc=True면 예외, bad_json=True면 깨진 응답."""

    def __init__(self, name="테스트토픽", raise_exc=False, bad_json=False):
        outer = self
        self.calls = 0

        class _Messages:
            def create(self, *, model, max_tokens, system, messages):
                outer.calls += 1
                if raise_exc:
                    import anthropic
                    raise anthropic.AnthropicError("boom")
                text = "not json" if bad_json else json.dumps(
                    {"new_name": name, "new_desc": "설명"}, ensure_ascii=False
                )
                return SimpleNamespace(content=[SimpleNamespace(text=text)])

        self.messages = _Messages()


def _emb(*vals):
    return "[" + ",".join(str(v) for v in vals) + "]"


def _skrow(node_id, vec):
    return SimpleNamespace(node_id=node_id, emb=_emb(*vec))


def _crow(cid, vec, title="t"):
    return SimpleNamespace(id=cid, title=title, difficulty=2, text_embedding=_emb(*vec))


# ─────────────────────────────────────────────────────────────────────────────
# _nearest
# ─────────────────────────────────────────────────────────────────────────────


def test_nearest_picks_max_cosine():
    cents = {1: np.array([1.0, 0, 0, 0]), 2: np.array([0, 1.0, 0, 0])}
    nid, sim = _nearest(np.array([0.9, 0.1, 0, 0]), cents)
    assert nid == 1 and sim > 0.9


def test_nearest_empty_returns_none():
    nid, sim = _nearest(np.array([1.0, 0, 0, 0]), {})
    assert nid is None and sim == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# _cluster_residuals — 연결요소 + MIN 필터
# ─────────────────────────────────────────────────────────────────────────────


def _u(v):
    a = np.array(v, dtype=float)
    return a / np.linalg.norm(a)


def test_cluster_residuals_splits_clusters_and_orphans():
    residuals = [
        (1, _u([0, 0, 1, 0])), (2, _u([0, 0, 1, 0])), (3, _u([0, 0, 1, 0])),  # 3개 군집
        (4, _u([0, 0, 0, 1])), (5, _u([0, 0, 0, 1])),                          # 2개(고아)
    ]
    clusters, orphans = _cluster_residuals(residuals, group_threshold=0.65, min_size=3)
    assert clusters == [[1, 2, 3]]          # 크기>=3만 승격
    assert sorted(orphans) == [4, 5]        # 크기<3 → 고아


def test_cluster_residuals_sorted_by_size_desc():
    residuals = [(i, _u([0, 0, 1, 0])) for i in range(3)] + \
                [(i, _u([0, 0, 0, 1])) for i in range(10, 14)]
    clusters, orphans = _cluster_residuals(residuals, group_threshold=0.65, min_size=3)
    assert [len(c) for c in clusters] == [4, 3]  # 큰 것 먼저
    assert orphans == []


# ─────────────────────────────────────────────────────────────────────────────
# _name_cluster — 정상 + 폴백
# ─────────────────────────────────────────────────────────────────────────────


def test_name_cluster_ok():
    name, desc = _name_cluster(["MCP 서버 만들기", "MCP 서버 후기"], _FakeAnthropic(name="MCP 서버"))
    assert name == "MCP 서버" and desc


def test_name_cluster_falls_back_on_llm_error():
    name, desc = _name_cluster(["로컬 LLM 서빙기"], _FakeAnthropic(raise_exc=True))
    assert name.startswith("자동:") and "로컬 LLM 서빙기" in name


def test_name_cluster_falls_back_on_bad_json():
    name, _ = _name_cluster(["제목"], _FakeAnthropic(bad_json=True))
    assert name.startswith("자동:")


# ─────────────────────────────────────────────────────────────────────────────
# expand_graph — 2-패스 end-to-end
# ─────────────────────────────────────────────────────────────────────────────


def _two_pass_conn():
    # 스켈레톤 2개(대주제, parent NULL): node1=axis0, node2=axis1
    skeleton = [_skrow(1, [1, 0, 0, 0]), _skrow(2, [0, 1, 0, 0])]
    roots = list(skeleton)
    contents = [
        _crow(101, [1, 0, 0, 0], "흡수대상"),        # node1에 흡수(cos 1.0 >= 0.70)
        _crow(102, [0, 0, 1, 0], "군집A-1"),         # 군집(axis2) — 스켈레톤과 직교
        _crow(103, [0, 0, 1, 0], "군집A-2"),
        _crow(104, [0, 0, 1, 0], "군집A-3"),
        _crow(105, [0, 0, 0, 1], "고아-1"),          # 쌍(axis3) → 크기2 < MIN → 고아
        _crow(106, [0, 0, 0, 1], "고아-2"),
    ]
    return _Conn(skeleton, roots, contents)


def test_expand_graph_two_pass_counts():
    conn = _two_pass_conn()
    stats = expand_graph(conn, _FakeAnthropic())
    assert stats["total"] == 6
    assert stats["absorbed"] == 1        # c101 → 스켈레톤
    assert stats["new_nodes"] == 1       # 군집 1개만 노드 승격
    assert stats["clustered"] == 3       # 102,103,104
    assert stats["orphan_mapped"] == 2   # 105,106 → 최근접 스켈레톤
    assert stats["skipped"] == 0
    assert stats["llm_calls"] == 1       # 클러스터당 1회(콘텐츠 수 아님)


def test_expand_graph_no_orphan_nodes_created():
    """고아(크기<MIN)는 노드를 만들지 않는다 — 단일 콘텐츠 노드 금지(A)."""
    conn = _two_pass_conn()
    expand_graph(conn, _FakeAnthropic())
    # 생성된 노드는 군집 1개뿐. 고아(105,106)는 노드가 아니라 기존 노드 매핑.
    assert len(conn.created) == 1
    _, _, parent_id = conn.created[0]
    assert parent_id in (1, 2)           # 부모는 대주제(root)
    orphan_targets = [nid for cid, nid, _ in conn.mappings if cid in (105, 106)]
    assert orphan_targets and all(t in (1, 2) for t in orphan_targets)


def test_expand_graph_new_node_not_used_as_absorb_target():
    """풀 미오염(B): 새 클러스터 노드 id로 '흡수'되는 콘텐츠는 클러스터 멤버뿐."""
    conn = _two_pass_conn()
    expand_graph(conn, _FakeAnthropic())
    new_id = 900  # _Conn new_id_start
    to_new = [cid for cid, nid, _ in conn.mappings
              if nid == new_id and cid not in (102, 103, 104)]
    assert to_new == []


def test_expand_graph_empty_skeleton_skips():
    """스켈레톤이 비면 흡수 불가 + 고아 매핑 대상도 없어 skip."""
    contents = [_crow(201, [0, 0, 1, 0]), _crow(202, [0, 0, 0, 1])]
    conn = _Conn([], [], contents)
    stats = expand_graph(conn, _FakeAnthropic())
    assert stats["absorbed"] == 0
    assert stats["new_nodes"] == 0       # 둘 다 고아(크기<3)
    assert stats["skipped"] == 2         # 스켈레톤 없어 고아 매핑 불가
