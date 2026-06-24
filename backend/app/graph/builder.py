"""HIVE-19: 이종 그래프 빌더.

DB(curriculum_nodes · content · content_node_mapping · node_links)를 networkx
이종(heterogeneous) 그래프로 로드한다. GraphRAG(추천)·시각화·평가·GraphSAGE가
공통으로 쓰는 그래프 표현 레이어.

노드 2종 (node attr 'kind'):
- topic   : 커리큘럼 노드 (대주제 7개 + Auto-HKG 하위노드)  →  키 "topic:<id>"
- content : 콘텐츠 글                                      →  키 "content:<id>"

엣지 3종 (edge attr 'rel'):
- belongs_to : content → topic   (weight = relevance_score)
- similar_to : content → content (weight = 코사인 유사도, pgvector top-k)
- precedes   : topic → topic     (weight, node_links 기반)

설계 메모:
- 대주제 간 선행관계는 손으로 박지 않는다. precedes 엣지(node_links)는 Auto-HKG(LLM)가
  생성하고, '다음 뭐 배울지'는 추천이 유저 mastery로 동적 결정한다(self-organizing 일관).
  그래서 현재 precedes는 비어 있는 게 정상.
- similar_to는 저장하지 않고 빌드 시 pgvector로 도출한다(데이터 기반, 손 안 댐).
- content-agnostic: 논문이든 경험글이든 동일하게 그래프로 표현된다.

실행(통계 확인):
    cd backend
    python -m app.graph.builder
"""
from __future__ import annotations

import networkx as nx
from sqlalchemy import text
from sqlalchemy.orm import Session

SIMILAR_K = 5  # 콘텐츠당 similar_to 이웃 수 (파이프라인 설계: 상위 5건)


def _add_topics(g: nx.MultiDiGraph, db: Session) -> int:
    rows = db.execute(
        text("SELECT id, name, parent_id, is_auto_generated FROM curriculum_nodes")
    ).fetchall()
    for r in rows:
        g.add_node(
            f"topic:{r.id}",
            kind="topic",
            node_id=r.id,
            name=r.name,
            parent_id=r.parent_id,
            auto=bool(r.is_auto_generated),
        )
    return len(rows)


def _add_content(g: nx.MultiDiGraph, db: Session) -> int:
    rows = db.execute(
        text("SELECT id, title, difficulty, content_type, source FROM content")
    ).fetchall()
    for r in rows:
        g.add_node(
            f"content:{r.id}",
            kind="content",
            content_id=r.id,
            title=r.title,
            difficulty=r.difficulty,
            content_type=r.content_type,
            source=r.source,
        )
    return len(rows)


def _add_belongs_to(g: nx.MultiDiGraph, db: Session) -> int:
    rows = db.execute(
        text("SELECT content_id, node_id, relevance_score FROM content_node_mapping")
    ).fetchall()
    added = 0
    for r in rows:
        src, dst = f"content:{r.content_id}", f"topic:{r.node_id}"
        if g.has_node(src) and g.has_node(dst):
            g.add_edge(src, dst, rel="belongs_to", weight=float(r.relevance_score or 0.0))
            added += 1
    return added


def _add_precedes(g: nx.MultiDiGraph, db: Session) -> int:
    # node_links: 노드 간 선행/후행. Auto-HKG(HIVE-21)가 채운다 — 현재는 비어 있을 수 있음.
    rows = db.execute(
        text("SELECT source_node_id, target_node_id, weight FROM node_links")
    ).fetchall()
    added = 0
    for r in rows:
        src, dst = f"topic:{r.source_node_id}", f"topic:{r.target_node_id}"
        if g.has_node(src) and g.has_node(dst):
            g.add_edge(src, dst, rel="precedes", weight=float(r.weight or 0.5))
            added += 1
    return added


def _add_similar_to(g: nx.MultiDiGraph, db: Session, k: int) -> int:
    # pgvector 코사인 top-k 이웃(콘텐츠당 k개). 임베딩 있는 콘텐츠만. 방향성 kNN 그래프.
    # ivfflat은 근사 검색(기본 probes=1)이라 소규모 데이터셋에선 이웃을 누락한다.
    # probes를 list 수까지 올려 정확한 top-k를 보장한다(데이터 작아 비용 무시 가능).
    db.execute(text("SET ivfflat.probes = 100"))
    rows = db.execute(
        text(
            """
            SELECT a.id AS src, nb.id AS dst,
                   1 - (a.text_embedding <=> nb.text_embedding) AS sim
            FROM content a
            CROSS JOIN LATERAL (
                SELECT b.id, b.text_embedding
                FROM content b
                WHERE b.id <> a.id AND b.text_embedding IS NOT NULL
                ORDER BY a.text_embedding <=> b.text_embedding
                LIMIT :k
            ) nb
            WHERE a.text_embedding IS NOT NULL
            """
        ),
        {"k": k},
    ).fetchall()
    added = 0
    for r in rows:
        src, dst = f"content:{r.src}", f"content:{r.dst}"
        if g.has_node(src) and g.has_node(dst):
            g.add_edge(src, dst, rel="similar_to", weight=float(r.sim))
            added += 1
    return added


def build_graph(
    db: Session, similar_k: int = SIMILAR_K, include_similar: bool = True
) -> nx.MultiDiGraph:
    """DB를 networkx 이종 그래프(MultiDiGraph)로 빌드한다.

    반환 그래프의 g.graph["stats"]에 종류별 노드/엣지 수가 담긴다.

    include_similar=False면 similar_to(콘텐츠 kNN, 가장 비싼 단계)를 건너뛴다.
    주제 노드/숙련도만 필요한 화면(학습경로 '주제별 숙련도')에서 응답을 빠르게 받기 위함.
    """
    g = nx.MultiDiGraph()
    n_topic = _add_topics(g, db)
    n_content = _add_content(g, db)
    n_belongs = _add_belongs_to(g, db)
    n_precedes = _add_precedes(g, db)
    n_similar = _add_similar_to(g, db, similar_k) if include_similar else 0
    g.graph["stats"] = {
        "topics": n_topic,
        "content": n_content,
        "belongs_to": n_belongs,
        "precedes": n_precedes,
        "similar_to": n_similar,
    }
    return g


def _main() -> None:
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        g = build_graph(db)
    finally:
        db.close()

    s = g.graph["stats"]
    print("=" * 48)
    print("HIVE-19 이종 그래프 빌드 결과")
    print("=" * 48)
    print(f"노드: {g.number_of_nodes()}  (topic {s['topics']} / content {s['content']})")
    print(f"엣지: {g.number_of_edges()}")
    print(f"  belongs_to : {s['belongs_to']}")
    print(f"  similar_to : {s['similar_to']}")
    print(f"  precedes   : {s['precedes']}  (Auto-HKG가 채울 예정)")


if __name__ == "__main__":
    _main()
