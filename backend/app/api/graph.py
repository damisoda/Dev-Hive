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
        nodes.append({
            "id": str(n),
            "kind": kind,
            "label": (label or "")[:80],
            "auto": bool(d.get("auto", False)),
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
def get_graph(db: Session = Depends(get_db)):
    """현재 지식그래프 전체(topic/content 노드 + belongs_to/similar_to/precedes 엣지)."""
    g = build_graph(db)
    return serialize_graph(g)
