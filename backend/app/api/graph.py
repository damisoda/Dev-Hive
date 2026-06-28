"""HIVE-32: 그래프 데이터 API.

build_graph(HIVE-19) 결과를 프론트 시각화(Obsidian 스타일 force-directed)용 JSON으로
직렬화해 서빙한다. 추천/태깅처럼 로직은 graph 레이어에 있고 여기선 직렬화+서빙만 한다.
"""
import networkx as nx
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.graph.builder import build_graph

router = APIRouter(prefix="/graph", tags=["graph"])


class GraphNode(BaseModel):
    id: str
    kind: str            # topic | content
    label: str
    auto: bool = False   # Auto-HKG 생성 노드 (topic에만 의미)
    parent: str | None = None  # 하위노드의 소속 대주제 "topic:<id>" (대주제는 None)


class GraphEdge(BaseModel):
    source: str
    target: str
    rel: str             # belongs_to | similar_to | precedes
    weight: float


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    stats: dict


def serialize_graph(g: nx.MultiDiGraph) -> dict:
    """networkx MultiDiGraph → 시각화용 dict(nodes/edges/stats). 순수 함수(테스트 대상)."""
    nodes = []
    for n, d in g.nodes(data=True):
        kind = d.get("kind", "")
        label = d.get("name") if kind == "topic" else (d.get("title") or "")
        parent_id = d.get("parent_id")
        nodes.append({
            "id": str(n),
            "kind": kind,
            "label": (label or "")[:80],
            "auto": bool(d.get("auto", False)),
            "parent": f"topic:{parent_id}" if parent_id is not None else None,
        })
    edges = [
        {
            "source": str(u),
            "target": str(v),
            "rel": d.get("rel", ""),
            "weight": float(d.get("weight", 0.0)),
        }
        for u, v, d in g.edges(data=True)
    ]
    return {"nodes": nodes, "edges": edges, "stats": g.graph.get("stats", {})}


@router.get("", response_model=GraphResponse)
def get_graph(light: bool = False, db: Session = Depends(get_db)):
    """현재 지식그래프(topic/content 노드 + belongs_to/similar_to/precedes 엣지).

    light=True면 가장 비싼 similar_to(콘텐츠 kNN)를 건너뛴다 — 주제 노드만 필요한
    화면이 26초짜리 유사도 계산을 기다리지 않도록(HIVE-65 주제별 숙련도용).
    """
    g = build_graph(db, include_similar=not light)
    return serialize_graph(g)
