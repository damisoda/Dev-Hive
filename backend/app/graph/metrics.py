"""HIVE-38: 그래프 자기조직화 지표.

build_graph(HIVE-19)가 만든 지식그래프에서 "스스로 조직된다(self-organizing)"를
정량 지표로 측정한다. Auto-HKG 전후·콘텐츠 누적 전후를 같은 함수로 재서 비교한다.

측정 대상 그래프: topic+content 노드 + belongs_to/similar_to/precedes 엣지를
무방향 단순 그래프로 투영(가중치 보존). 커뮤니티/중심성/연결성 분석에 적합.

지표 (근거: Buehler 2502.13025 자기조직화, Abu-Rasheed 2501.12300 ADC/modularity):
- modularity      : Louvain 커뮤니티의 모듈성(0~1). 높을수록 클러스터가 뚜렷
- num_communities : 탐지된 커뮤니티 수
- adc             : 평균 차수 중심성(연결 밀도)
- max_degree/hub  : 최대 차수(허브 형성)
- degree_dist     : 차수 분포 요약(power-law/scale-free 관찰용)
- articulation_points : 끊으면 그래프가 쪼개지는 노드 수(주제 경계 연결 노드)
- top_betweenness : 매개 중심성 상위(브릿지 역할)
- lcc_size/lcc_ratio : 최대 연결 성분 크기/비율(분절 안 되고 하나로 성장)
- avg_clustering   : 평균 군집 계수

주의(스케일 작음): Buehler급 scale-free 창발은 기대하지 않는다. modularity/허브/
브릿지로 '주제를 넘어 조직된다'를 보이는 데 집중한다.
"""
from __future__ import annotations

from collections import Counter

import networkx as nx


def _to_simple_undirected(g: nx.MultiDiGraph) -> nx.Graph:
    """MultiDiGraph → 단순 무방향 Graph. 다중 엣지 가중치는 합산(표준).

    Note(M2): precedes(topic→topic 방향) 엣지의 방향성은 무방향 투영에서 소실된다.
    현재 precedes는 비어 있어 영향 없으나, Auto-HKG가 채우면 방향성 지표는 별도 필요.
    """
    h = nx.Graph()
    for n, d in g.nodes(data=True):
        h.add_node(n, **d)
    for u, v, d in g.edges(data=True):
        w = float(d.get("weight", 1.0))
        if h.has_edge(u, v):
            h[u][v]["weight"] += w        # 병렬 엣지는 합산(연결 강도 누적)
        else:
            h.add_edge(u, v, weight=w)
    return h


def _degree_distribution(degrees: list[int]) -> dict:
    """차수 분포 요약 (히스토그램 + 기초통계). power-law 관찰용."""
    if not degrees:
        return {"min": 0, "max": 0, "mean": 0.0, "histogram": {}}
    return {
        "min": min(degrees),
        "max": max(degrees),
        "mean": round(sum(degrees) / len(degrees), 3),
        # 차수별 노드 수 (정렬). 꼬리가 길면 scale-free 경향
        "histogram": dict(sorted(Counter(degrees).items())),
    }


def compute_metrics(g: nx.MultiDiGraph, *, betweenness_top: int = 5) -> dict:
    """그래프 자기조직화 지표를 계산해 dict로 반환한다.

    betweenness_top: 매개 중심성 상위 몇 개를 반환할지.
    """
    h = _to_simple_undirected(g)
    n, m = h.number_of_nodes(), h.number_of_edges()

    # 노드 종류별 카운트
    kinds: dict[str, int] = {}
    for _, d in h.nodes(data=True):
        k = d.get("kind", "?")
        kinds[k] = kinds.get(k, 0) + 1

    if n == 0:
        return {"nodes": 0, "edges": 0, "kinds": kinds}

    # 커뮤니티 / 모듈성 (가중 Louvain, 시드 고정으로 재현성)
    communities = nx.community.louvain_communities(h, weight="weight", seed=42)
    modularity = nx.community.modularity(h, communities, weight="weight")

    # 차수 중심성 / 차수 분포 / 허브
    degrees = [deg for _, deg in h.degree()]
    deg_cent = nx.degree_centrality(h)
    adc = sum(deg_cent.values()) / len(deg_cent)
    hub_node, hub_deg = max(h.degree(), key=lambda x: x[1])

    # 매개 중심성 상위 (브릿지). 무가중으로 계산한다 — weight가 '유사도'(클수록 가까움)라
    # betweenness의 거리 해석(클수록 멂)과 반대라 가중을 쓰면 결과가 뒤집힌다.
    # 구조적 브릿지(주제 경계 잇는 노드) 식별엔 무가중이 적합. 큰 그래프는 k-샘플링으로 근사.
    bc_k = min(n, 300) if n > 400 else None
    betw = nx.betweenness_centrality(h, k=bc_k, weight=None, seed=42)
    top_betw = sorted(betw.items(), key=lambda x: x[1], reverse=True)[:betweenness_top]

    # articulation points (끊으면 분절되는 노드)
    artic = list(nx.articulation_points(h))

    # 최대 연결 성분
    comps = list(nx.connected_components(h))
    lcc = max(comps, key=len) if comps else set()

    # 평균 군집 계수
    avg_clustering = nx.average_clustering(h)

    def _label(node: str) -> str:
        d = h.nodes[node]
        return (d.get("name") or d.get("title") or str(node))[:50]

    return {
        "nodes": n,
        "edges": m,
        "kinds": kinds,
        "modularity": round(modularity, 4),
        "num_communities": len(communities),
        "adc": round(adc, 4),
        "max_degree": hub_deg,
        "hub": _label(hub_node),
        "degree_dist": _degree_distribution(degrees),
        "articulation_points": len(artic),
        "top_betweenness": [
            {"node": _label(node), "score": round(score, 4)} for node, score in top_betw
        ],
        "lcc_size": len(lcc),
        "lcc_ratio": round(len(lcc) / n, 4),
        "avg_clustering": round(avg_clustering, 4),
        "num_components": len(comps),
    }
