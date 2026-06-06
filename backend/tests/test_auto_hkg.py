"""HIVE-21 Auto-HKG 단위 테스트.

LLM/DB 없이 `expand_one`의 가드레일·노드 생성 로직을 가짜 커넥션 + 가짜 Haiku로 검증한다.
- top 유사도 > 0.85 → LLM 없이 기존 매핑(단락)
- new_top은 top 유사도 < 0.40일 때만, 아니면 new_sub로 강등
- new_sub/new_top 시 curriculum_nodes 생성 + 매핑 + centroid/info 갱신
"""
import json
from types import SimpleNamespace

import numpy as np

from app.graph.auto_hkg import expand_one


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


def _row(**kw):
    return SimpleNamespace(**kw)


class _Conn:
    """curriculum_nodes INSERT / content_node_mapping INSERT를 흉내내는 가짜 커넥션."""

    def __init__(self, new_id=999):
        self._new_id = new_id
        self.created = []   # (name, desc, parent_id)
        self.mappings = []  # (content_id, node_id, score)

    def execute(self, clause, params=None):
        sql = str(clause)
        if "INSERT INTO curriculum_nodes" in sql:
            self.created.append((params["name"], params["desc"], params["parent_id"]))
            return _Result([_row(id=self._new_id)])
        if "INSERT INTO content_node_mapping" in sql:
            self.mappings.append((params["cid"], params["nid"], round(params["score"], 3)))
            return _Result([])
        return _Result([])


class _Messages:
    def __init__(self, resp):
        self._resp = resp
        self.calls = 0

    def create(self, **kw):
        self.calls += 1
        return SimpleNamespace(content=[SimpleNamespace(text=json.dumps(self._resp))])


class _Client:
    def __init__(self, resp):
        self.messages = _Messages(resp)


def _content(emb_str):
    return {"id": 100, "title": "t", "tags": [], "difficulty": "중급", "text_embedding": emb_str}


def _setup(node_vecs):
    centroids = {nid: np.array(v, dtype=float) for nid, v in node_vecs.items()}
    info = {nid: {"name": f"노드{nid}", "desc": "d", "parent_id": None} for nid in node_vecs}
    return centroids, info


def test_high_sim_maps_existing_without_llm():
    # 콘텐츠 [1,0,0] vs 노드1 [1,0,0] = sim 1.0 → DEDUP(0.85) 초과 → LLM 단락, 기존 매핑
    centroids, info = _setup({1: [1, 0, 0], 2: [0, 1, 0]})
    conn = _Conn()
    client = _Client({"decision": "new_top", "new_name": "X"})  # 호출되면 안 됨
    res = expand_one(_content("[1,0,0]"), centroids, info, conn, client)
    assert res["action"] == "existing" and res["node_id"] == 1 and res["llm"] is False
    assert client.messages.calls == 0
    assert conn.mappings == [(100, 1, 1.0)]
    assert conn.created == []


def test_llm_existing():
    # top_sim 0.707 < 0.85 → LLM 호출, existing(node 2)
    centroids, info = _setup({1: [1, 1, 0], 2: [0, 1, 1]})
    conn = _Conn()
    client = _Client({"decision": "existing", "node_id": 2})
    res = expand_one(_content("[1,0,0]"), centroids, info, conn, client)
    assert res["action"] == "existing" and res["node_id"] == 2
    assert client.messages.calls == 1
    assert conn.mappings[0][:2] == (100, 2)
    assert conn.created == []


def test_llm_new_sub_creates_node():
    centroids, info = _setup({1: [1, 1, 0], 2: [0, 1, 1]})
    conn = _Conn(new_id=555)
    client = _Client({"decision": "new_sub", "parent_id": 1,
                      "new_name": "LangGraph", "new_desc": "에이전트 프레임워크"})
    res = expand_one(_content("[1,0,0]"), centroids, info, conn, client)
    assert res["action"] == "new_sub" and res["node_id"] == 555 and res["parent_id"] == 1
    assert conn.created == [("LangGraph", "에이전트 프레임워크", 1)]
    assert conn.mappings == [(100, 555, 1.0)]
    # 새 노드가 in-place로 centroids/info에 반영 → 이후 콘텐츠가 매칭 가능
    assert 555 in centroids and info[555]["name"] == "LangGraph"


def test_new_top_downgraded_when_close():
    # top_sim 0.707 (0.40~0.85) → new_top 제안이라도 new_sub(부모=가장 가까운 노드)로 강등
    centroids, info = _setup({1: [1, 1, 0], 2: [0, 0, 1]})
    conn = _Conn(new_id=777)
    client = _Client({"decision": "new_top", "new_name": "신규영역", "new_desc": "d"})
    res = expand_one(_content("[1,0,0]"), centroids, info, conn, client)
    assert res["action"] == "new_sub" and res["parent_id"] == 1
    assert conn.created == [("신규영역", "d", 1)]


def test_new_top_allowed_when_far():
    # 모든 노드와 충분히 멂(top_sim 0 < 0.40) → new_top 허용(parent NULL)
    centroids, info = _setup({1: [0, 1, 0], 2: [0, 0, 1]})
    conn = _Conn(new_id=888)
    client = _Client({"decision": "new_top", "new_name": "양자ML", "new_desc": "d"})
    res = expand_one(_content("[1,0,0]"), centroids, info, conn, client)
    assert res["action"] == "new_top" and res["node_id"] == 888
    assert conn.created == [("양자ML", "d", None)]


class _RawMessages:
    """JSON이 아닌 원문 텍스트를 그대로 돌려주는 가짜(파싱 폴백 검증용)."""

    def __init__(self, raw):
        self._raw = raw
        self.calls = 0

    def create(self, **kw):
        self.calls += 1
        return SimpleNamespace(content=[SimpleNamespace(text=self._raw)])


class _RawClient:
    def __init__(self, raw):
        self.messages = _RawMessages(raw)


def test_hallucinated_node_id_falls_back_to_top():
    # LLM이 존재하지 않는 node_id(9999) 반환 → 최근접 노드(top)로 보정 (FK 위반 방지)
    centroids, info = _setup({1: [1, 1, 0], 2: [0, 1, 1]})
    conn = _Conn()
    client = _Client({"decision": "existing", "node_id": 9999})
    res = expand_one(_content("[1,0,0]"), centroids, info, conn, client)
    assert res["action"] == "existing" and res["node_id"] == 1   # top(노드1)로 보정
    assert conn.mappings[0][:2] == (100, 1)


def test_hallucinated_parent_falls_back_to_top():
    centroids, info = _setup({1: [1, 1, 0], 2: [0, 1, 1]})
    conn = _Conn(new_id=321)
    client = _Client({"decision": "new_sub", "parent_id": 9999, "new_name": "X", "new_desc": "d"})
    res = expand_one(_content("[1,0,0]"), centroids, info, conn, client)
    assert res["action"] == "new_sub" and res["parent_id"] == 1   # 환각 부모 → top
    assert conn.created == [("X", "d", 1)]


def test_malformed_llm_response_falls_back():
    # 비-JSON 응답 → 파싱 폴백 → 기존(top) 매핑, 크래시 없음
    centroids, info = _setup({1: [1, 1, 0], 2: [0, 1, 1]})
    conn = _Conn()
    client = _RawClient("이건 JSON이 아니라 그냥 텍스트")
    res = expand_one(_content("[1,0,0]"), centroids, info, conn, client)
    assert res["action"] == "existing" and res["node_id"] == 1


def test_empty_graph_skipped():
    # 노드 0개(빈 그래프) → 후보 없음, 매핑 대상 없음 → skipped (크래시 없음)
    conn = _Conn()
    client = _Client({"decision": "existing", "node_id": 5})
    res = expand_one(_content("[1,0,0]"), {}, {}, conn, client)
    assert res["action"] == "skipped"
    assert conn.mappings == [] and conn.created == []
