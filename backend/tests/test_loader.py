"""HIVE-29 로더 동적 노드 조회 단위 테스트.

`load_content`는 DB에 의존하지만, 핵심 변경(대주제 id를 name으로 동적 조회 = 하드코딩 제거)은
가짜 커넥션으로 검증한다. 노드 id가 옛 하드코딩 위치(1~7)와 달라도, Auto-HKG가 만든 새 노드여도
name으로 올바로 매핑되는지가 핵심.
"""
from types import SimpleNamespace

from app.tagging.loader import load_content


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


def _row(**kw):
    return SimpleNamespace(**kw)


class _FakeConn:
    """content INSERT / 노드 조회 / 매핑 INSERT를 흉내내는 가짜 커넥션."""

    def __init__(self, nodes, content_id=100, url_conflict=False):
        self._nodes = nodes  # [(id, name), ...]
        self._content_id = content_id
        self._url_conflict = url_conflict
        self.mappings = []  # 캡처한 (content_id, node_id, score)

    def execute(self, clause, params=None):
        sql = str(clause)
        if "INSERT INTO content " in sql:
            return _Result([] if self._url_conflict else [_row(id=self._content_id)])
        if "SELECT id, name FROM curriculum_nodes" in sql:
            return _Result([_row(id=i, name=n) for i, n in self._nodes])
        if "INSERT INTO content_node_mapping" in sql:
            self.mappings.append((params["content_id"], params["node_id"], params["score"]))
            return _Result([])
        return _Result([])


_EMB = [0.0] * 1536
_ITEM = {"title": "t", "url": "u", "source": "reddit", "body": "b"}


def test_maps_by_name_not_hardcoded_id():
    # "Agentic AI"가 id=99(옛 하드코딩 2가 아님)인데도 매핑돼야 → 동적 조회 증명
    conn = _FakeConn(nodes=[(99, "Agentic AI"), (50, "프롬프트 엔지니어링")])
    tags = {"quality_score": 0.8, "relevance": {"Agentic AI": 0.7, "프롬프트 엔지니어링": 0.3}}
    cid = load_content(_ITEM, tags, _EMB, conn)
    assert cid == 100
    # 0.7 >= 0.5 → Agentic AI(99) 매핑 / 0.3 < 0.5 → 프롬프트 매핑 안 됨
    assert conn.mappings == [(100, 99, 0.7)]


def test_auto_hkg_new_node_is_mapped():
    # Auto-HKG가 만든 새 노드(id=123)에도 name으로 매핑됨 (HIVE-29의 목적)
    conn = _FakeConn(nodes=[(123, "양자 머신러닝")])
    tags = {"quality_score": 0.9, "relevance": {"양자 머신러닝": 0.9}}
    load_content(_ITEM, tags, _EMB, conn)
    assert conn.mappings == [(100, 123, 0.9)]


def test_quality_below_threshold_returns_none():
    conn = _FakeConn(nodes=[(1, "Agentic AI")])
    tags = {"quality_score": 0.4, "relevance": {"Agentic AI": 0.9}}
    assert load_content(_ITEM, tags, _EMB, conn) is None
    assert conn.mappings == []


def test_url_conflict_returns_none():
    conn = _FakeConn(nodes=[(1, "Agentic AI")], url_conflict=True)
    tags = {"quality_score": 0.9, "relevance": {"Agentic AI": 0.9}}
    assert load_content(_ITEM, tags, _EMB, conn) is None
    assert conn.mappings == []


def test_unknown_topic_skipped():
    # curriculum_nodes에 없는 주제는 매핑 스킵(에러 없음)
    conn = _FakeConn(nodes=[(1, "Agentic AI")])
    tags = {"quality_score": 0.9, "relevance": {"존재안함": 0.9, "Agentic AI": 0.6}}
    load_content(_ITEM, tags, _EMB, conn)
    assert conn.mappings == [(100, 1, 0.6)]


def test_no_relevant_topics_still_inserts_content():
    # 모든 relevance < 0.5 → 매핑 0이지만 content는 적재(id 반환)
    conn = _FakeConn(nodes=[(1, "Agentic AI")])
    tags = {"quality_score": 0.9, "relevance": {"Agentic AI": 0.2}}
    assert load_content(_ITEM, tags, _EMB, conn) == 100
    assert conn.mappings == []
