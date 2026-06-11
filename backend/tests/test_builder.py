"""HIVE-19 이종 그래프 빌더(graph.builder) 단위 테스트.

build_graph는 DB에 의존하지만, 그래프 *조립 로직*은 가짜 세션(미리 정한 행을 돌려줌)으로
DB 없이 검증한다. 노드 종류·속성, 엣지 관계/방향/가중치, 누락 노드 가드, stats를 다룬다.
"""
from types import SimpleNamespace

import pytest

from app.graph.builder import build_graph


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeSession:
    """SQL 문자열로 분기해 미리 정한 행을 반환하는 가짜 세션.

    분기 순서 주의: 'content_node_mapping'·'LATERAL'을 'FROM content'보다 먼저 검사해야
    각각 belongs_to·similar_to 쿼리로 올바로 라우팅된다.
    """

    def __init__(self, topics, content, belongs, precedes, similar):
        self._topics = topics
        self._content = content
        self._belongs = belongs
        self._precedes = precedes
        self._similar = similar

    def execute(self, clause, params=None):
        sql = str(clause)
        if sql.lstrip().upper().startswith("SET "):
            return _Result([])
        if "curriculum_nodes" in sql:
            return _Result(self._topics)
        if "content_node_mapping" in sql:
            return _Result(self._belongs)
        if "node_links" in sql:
            return _Result(self._precedes)
        if "LATERAL" in sql:
            return _Result(self._similar)
        if "FROM content" in sql:
            return _Result(self._content)
        return _Result([])


def _row(**kw):
    return SimpleNamespace(**kw)


@pytest.fixture
def graph():
    topics = [
        _row(id=1, name="프롬프트 엔지니어링", parent_id=None, is_auto_generated=False),
        _row(id=2, name="Agentic AI", parent_id=None, is_auto_generated=False),
    ]
    content = [
        _row(id=10, title="Cursor 후기", difficulty="입문", content_type="experience", source="reddit"),
        _row(id=11, title="LangGraph 튜토리얼", difficulty="중급", content_type="tutorial", source="velog"),
    ]
    belongs = [
        _row(content_id=10, node_id=1, relevance_score=0.9),
        _row(content_id=10, node_id=2, relevance_score=0.6),
        _row(content_id=11, node_id=2, relevance_score=0.8),
        _row(content_id=99, node_id=1, relevance_score=0.7),  # content 99 없음 → 스킵돼야
    ]
    precedes = [
        _row(source_node_id=1, target_node_id=2, weight=0.7),
    ]
    similar = [
        _row(src=10, dst=11, sim=0.75),
        _row(src=11, dst=10, sim=0.70),
        _row(src=11, dst=42, sim=0.5),  # content 42 없음 → 스킵돼야
    ]
    db = _FakeSession(topics, content, belongs, precedes, similar)
    return build_graph(db, similar_k=5)


def _edges(g, rel):
    return [(u, v, d) for u, v, d in g.edges(data=True) if d["rel"] == rel]


def test_node_kinds_and_count(graph):
    assert graph.number_of_nodes() == 4
    kinds = {n: d["kind"] for n, d in graph.nodes(data=True)}
    assert kinds["topic:1"] == "topic"
    assert kinds["content:10"] == "content"


def test_topic_attributes(graph):
    assert graph.nodes["topic:1"]["name"] == "프롬프트 엔지니어링"
    assert graph.nodes["topic:1"]["auto"] is False


def test_content_attributes(graph):
    n = graph.nodes["content:10"]
    assert n["title"] == "Cursor 후기"
    assert n["difficulty"] == "입문"
    assert n["content_type"] == "experience"
    assert n["source"] == "reddit"


def test_belongs_to_direction_and_weight(graph):
    e = _edges(graph, "belongs_to")
    assert len(e) == 3  # content 99 행은 스킵
    for u, v, d in e:
        assert graph.nodes[u]["kind"] == "content"
        assert graph.nodes[v]["kind"] == "topic"
    weights = {(u, v): d["weight"] for u, v, d in e}
    assert weights[("content:10", "topic:1")] == pytest.approx(0.9)


def test_similar_to_is_content_to_content(graph):
    e = _edges(graph, "similar_to")
    assert len(e) == 2  # content 42 행은 스킵
    for u, v, d in e:
        assert graph.nodes[u]["kind"] == "content"
        assert graph.nodes[v]["kind"] == "content"


def test_precedes_from_node_links(graph):
    # node_links → precedes. 현재 실DB는 비어있지만 Auto-HKG가 채우면 동작함을 검증.
    e = _edges(graph, "precedes")
    assert len(e) == 1
    u, v, d = e[0]
    assert (u, v) == ("topic:1", "topic:2")
    assert d["weight"] == pytest.approx(0.7)


def test_edges_to_missing_nodes_skipped(graph):
    assert not graph.has_node("content:99")
    assert not graph.has_node("content:42")


def test_stats(graph):
    assert graph.graph["stats"] == {
        "topics": 2,
        "content": 2,
        "belongs_to": 3,
        "precedes": 1,
        "similar_to": 2,
    }
