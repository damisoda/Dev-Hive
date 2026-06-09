"""HIVE-32 그래프 API 직렬화 단위 테스트.

`serialize_graph`는 DB에 의존하지 않는 순수 함수이므로 가짜 networkx 그래프로 검증한다.
노드 종류/라벨/auto 표시, 엣지 관계/방향, stats 통과, 빈 그래프를 다룬다.
"""
import networkx as nx

from app.api.graph import serialize_graph


def _graph():
    g = nx.MultiDiGraph()
    g.add_node("topic:1", kind="topic", name="프롬프트 엔지니어링", auto=False)
    g.add_node("topic:8", kind="topic", name="LangGraph", auto=True)
    g.add_node("content:10", kind="content", title="Cursor 후기")
    g.add_node("content:11", kind="content", title="다른 글")
    g.add_edge("content:10", "topic:1", rel="belongs_to", weight=0.9)
    g.add_edge("content:10", "content:11", rel="similar_to", weight=0.7)
    g.add_edge("topic:8", "topic:1", rel="precedes", weight=0.5)
    g.graph["stats"] = {"topics": 2, "content": 2}
    return g


def test_serialize_nodes():
    by_id = {n["id"]: n for n in serialize_graph(_graph())["nodes"]}
    assert by_id["topic:1"]["kind"] == "topic"
    assert by_id["topic:1"]["label"] == "프롬프트 엔지니어링"   # topic은 name
    assert by_id["topic:8"]["auto"] is True                    # Auto-HKG 노드 표시
    assert by_id["content:10"]["label"] == "Cursor 후기"        # content는 title
    assert by_id["content:10"]["auto"] is False


def test_serialize_edges():
    rels = sorted((e["rel"], e["source"], e["target"]) for e in serialize_graph(_graph())["edges"])
    assert ("belongs_to", "content:10", "topic:1") in rels
    assert ("similar_to", "content:10", "content:11") in rels
    assert ("precedes", "topic:8", "topic:1") in rels


def test_stats_passthrough():
    assert serialize_graph(_graph())["stats"] == {"topics": 2, "content": 2}


def test_empty_graph():
    out = serialize_graph(nx.MultiDiGraph())
    assert out["nodes"] == [] and out["edges"] == [] and out["stats"] == {}
