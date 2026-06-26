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

import math
import random
from collections import Counter

import networkx as nx
import numpy as np


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


def _stat(xs: list[float]) -> dict:
    if not xs:
        return {"mean": 0.0, "median": 0.0, "min": 0, "max": 0}
    s = sorted(xs)
    n = len(s)
    median = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
    return {"mean": round(sum(xs) / n, 2), "median": round(median, 2), "min": s[0], "max": s[-1]}


def _topic_metrics(g: nx.MultiDiGraph) -> dict:
    """topic 계층/적재 기반 구조 지표 — 과파편화를 직접 측정(HIVE-46).

    - orphan_ratio: auto 토픽 중 콘텐츠 ≤1건(고아) 비율. v1=0.94, 정상≈0.
    - max_topic_depth: topic 트리 최대 깊이(parent_id 체인). v1=8(눈덩이), 정상 1~2.
    - content_per_topic / content_per_auto_topic: 토픽당 콘텐츠 수 분포. v1 auto≈1.1.
    """
    topics: dict = {}            # node_id -> {parent_id, auto}
    content_count: dict = {}     # node_id(topic) -> belongs_to 콘텐츠 수
    for _, d in g.nodes(data=True):
        if d.get("kind") == "topic":
            nid = d.get("node_id")
            topics[nid] = {"parent_id": d.get("parent_id"), "auto": bool(d.get("auto"))}
            content_count[nid] = 0
    for _, v, d in g.edges(data=True):
        if d.get("rel") == "belongs_to":
            tid = g.nodes[v].get("node_id")
            if tid in content_count:
                content_count[tid] += 1

    auto_ids = [tid for tid, t in topics.items() if t["auto"]]
    orphan = sum(1 for tid in auto_ids if content_count.get(tid, 0) <= 1)
    orphan_ratio = round(orphan / len(auto_ids), 4) if auto_ids else 0.0

    def _depth(start: int) -> int:
        d_, cur, seen = 0, start, set()
        while True:
            p = topics.get(cur, {}).get("parent_id")
            if p is None or p not in topics or cur in seen or d_ > 50:
                break
            seen.add(cur)
            cur = p
            d_ += 1
        return d_

    max_depth = max((_depth(tid) for tid in topics), default=0)

    return {
        "auto_topics": len(auto_ids),
        "orphan_ratio": orphan_ratio,
        "max_topic_depth": max_depth,
        "content_per_topic": _stat([content_count[t] for t in topics]),
        "content_per_auto_topic": _stat([content_count[t] for t in auto_ids]),
    }


def cluster_quality(topic_embeddings: dict[int, list]) -> dict:
    """클러스터 의미 품질 — 임베딩 기반(그래프 밖, run_eval에서 DB 임베딩 주입).

    파라미터 튜닝 목적함수 + 회귀 게이트용. 멤버 2건 이상 클러스터만 평가.
    - cohesion: 멤버↔centroid 평균 코사인(클러스터 내 응집). 높을수록 좋음.
    - separation: centroid 간 평균 코사인(클러스터 간 분리). 낮을수록 좋음.
    - silhouette: -1~1. 응집·분리 종합(코사인 거리). 높을수록 잘 묶임 → 튜닝 기준.
    """
    clusters = {
        tid: [np.asarray(e, dtype=float) for e in embs]
        for tid, embs in topic_embeddings.items()
        if len(embs) >= 2
    }
    n_points = sum(len(v) for v in clusters.values())
    if not clusters:
        return {"n_clusters": 0, "n_points": 0,
                "cohesion": None, "separation": None, "silhouette": None}

    def _unit(v: np.ndarray) -> np.ndarray:
        nrm = np.linalg.norm(v)
        return v / nrm if nrm else v

    # cohesion + centroids
    centroids = []
    cohesions = []
    for embs in clusters.values():
        M = np.array([_unit(e) for e in embs])
        cen = M.mean(axis=0)
        cohesions.append(float(np.mean(M @ _unit(cen))))
        centroids.append(_unit(cen))
    cohesion = round(float(np.mean(cohesions)), 4)

    # separation (centroid 쌍별 코사인 평균)
    separation = None
    if len(centroids) >= 2:
        C = np.array(centroids)
        S = C @ C.T
        iu = np.triu_indices(len(C), k=1)
        separation = round(float(S[iu].mean()), 4)

    # silhouette (코사인 거리), 2개 이상 클러스터일 때만
    silhouette = None
    if len(clusters) >= 2:
        pts, labels = [], []
        for tid, embs in clusters.items():
            for e in embs:
                pts.append(_unit(e))
                labels.append(tid)
        X = np.array(pts)
        labels = np.array(labels)
        dist = 1.0 - (X @ X.T)
        uniq = list(clusters.keys())
        sils = []
        for i in range(len(X)):
            same = labels == labels[i]
            same[i] = False
            a = float(dist[i, same].mean()) if same.any() else 0.0
            b = min(float(dist[i, labels == t].mean()) for t in uniq if t != labels[i])
            denom = max(a, b)
            sils.append((b - a) / denom if denom > 0 else 0.0)
        silhouette = round(float(np.mean(sils)), 4)

    return {
        "n_clusters": len(clusters),
        "n_points": n_points,
        "cohesion": cohesion,
        "separation": separation,
        "silhouette": silhouette,
    }


def cluster_label_purity(cluster_labels: dict) -> dict:
    """클러스터 라벨 동질성(순도) — 의미(semantic) 지표.

    클러스터링에 쓰이지 않은 **독립 라벨**(태거의 content_type·대주제 등)로 평가하므로
    비순환적이고 해석이 쉽다("각 클러스터가 X% 단일 라벨로 구성"). 임베딩 기하(silhouette)와 달리
    baseline(전체 최빈 라벨 비율 = 랜덤 클러스터 기대)을 함께 줘서 '높다/낮다'를 판단할 수 있다.

    cluster_labels: {cluster_id: [label, ...]}  (label=None은 무시).
    반환: purity_mean(클러스터 단순평균) / purity_weighted(크기가중) / baseline / n_clusters.
    """
    per: list[float] = []
    modal_sum = 0
    total = 0
    all_labels: list = []
    for labels in cluster_labels.values():
        labs = [l for l in labels if l is not None]
        if not labs:
            continue
        modal = Counter(labs).most_common(1)[0][1]
        per.append(modal / len(labs))
        modal_sum += modal
        total += len(labs)
        all_labels.extend(labs)
    if not per:
        return {"n_clusters": 0, "purity_mean": None, "purity_weighted": None, "baseline": None}
    baseline = Counter(all_labels).most_common(1)[0][1] / len(all_labels)
    return {
        "n_clusters": len(per),
        "purity_mean": round(float(np.mean(per)), 4),
        "purity_weighted": round(modal_sum / total, 4),
        "baseline": round(baseline, 4),
    }


def label_cluster_agreement(true_labels: list, cluster_labels: list) -> dict:
    """클러스터링과 독립 라벨의 일치도 — V-measure(Rosenberg & Hirschberg 2007).

    purity는 클러스터를 잘게 쪼갤수록 1에 수렴하는 편향이 있다. V-measure는
    homogeneity(각 클러스터가 단일 클래스인가) × completeness(각 클래스가 한 클러스터에
    모이는가)의 조화평균이라 그 편향을 보정한다. 0~1, 랜덤이면 ~0.

    true_labels/cluster_labels: 같은 점들에 대한 정렬된 라벨 리스트(true가 None인 항목은 제외).
    엔트로피 기반 수식으로 직접 계산(sklearn 의존 없음). 랜덤(셔플) baseline 동봉.
    """
    pairs = [(t, k) for t, k in zip(true_labels, cluster_labels) if t is not None]
    n = len(pairs)
    if n == 0:
        return {"n": 0, "v_measure": None, "homogeneity": None,
                "completeness": None, "baseline": None}
    true = [t for t, _ in pairs]
    pred = [k for _, k in pairs]

    def _entropy(labels: list) -> float:
        c = Counter(labels)
        return -sum((v / n) * math.log(v / n) for v in c.values() if v)

    def _cond_entropy(a: list, b: list) -> float:
        """H(A|B) = -Σ (n_ab/n) log(n_ab/n_b)."""
        nb = Counter(b)
        pair = Counter(zip(a, b))
        return -sum((cnt / n) * math.log(cnt / nb[bk]) for (ak, bk), cnt in pair.items())

    def _v(a: list, b: list) -> tuple[float, float, float]:
        h_a, h_b = _entropy(a), _entropy(b)
        homo = 1.0 if h_a == 0 else 1 - _cond_entropy(a, b) / h_a
        comp = 1.0 if h_b == 0 else 1 - _cond_entropy(b, a) / h_b
        v = 0.0 if (homo + comp) == 0 else 2 * homo * comp / (homo + comp)
        return round(v, 4), round(homo, 4), round(comp, 4)

    v, homo, comp = _v(true, pred)
    rp = list(pred)
    random.Random(42).shuffle(rp)
    v_base, _, _ = _v(true, rp)
    return {"n": n, "v_measure": v, "homogeneity": homo,
            "completeness": comp, "baseline": v_base}


# ── HIVE-58: precedes 링크 평가 + 단일 목적함수 J ────────────────────────────

def precedes_link_metrics(predicted, golden) -> dict:
    """precedes 링크 예측 품질(방향성 유지). HIVE-58.

    node_links 전 행 = precedes(source->target). 골든셋과 비교해 방향까지 채점한다.
    predicted: 예측 엣지 (source,target) iterable.
    golden:    골든셋 (source,target) iterable — label==1(참 precedes)만.
    reversed_rate: 예측 중 방향이 뒤집힌 비율 = (t,s)∈gold 이고 (s,t)∉gold.
    0쌍(빈 predicted 또는 golden)에도 NaN/0div 없이 0.0.
    """
    pred = {(int(s), int(t)) for s, t in predicted}
    gold = {(int(s), int(t)) for s, t in golden}
    tp = len(pred & gold)
    precision = tp / len(pred) if pred else 0.0
    recall = tp / len(gold) if gold else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    rev = sum(1 for (s, t) in pred if (t, s) in gold and (s, t) not in gold)
    reversed_rate = rev / len(pred) if pred else 0.0
    return {
        "n_pred": len(pred), "n_golden": len(gold), "tp": tp,
        "precision": round(precision, 4), "recall": round(recall, 4),
        "f1": round(f1, 4), "reversed_rate": round(reversed_rate, 4),
    }


# 단일 목적함수 J 가중치 — 좋을수록 J↑(≈0~1). 합=1.
OBJECTIVE_WEIGHTS = {
    "coverage_ratio": 0.25,     # semantic.coverage_ratio (↑ 좋음)
    "purity_weighted": 0.25,    # semantic.tag_purity_topic.purity_weighted (↑)
    "v_measure": 0.25,          # semantic.v_measure_topic.v_measure (↑)
    "orphan_ratio": 0.15,       # metrics.orphan_ratio (↓ 좋음 → 1-x)
    "depth": 0.10,              # metrics.max_topic_depth (얕을수록 ↑)
}
_DEPTH_OK = 2     # 이 깊이 이하 만점, 초과분만 선형 감점(6단계 폭)


def compute_objective(snapshot: dict) -> dict:
    """eval 스냅샷에서 정확키를 뽑아 단일 목적함수 J 계산(HIVE-58).

    정확키: semantic.coverage_ratio / semantic.tag_purity_topic.purity_weighted /
            semantic.v_measure_topic.v_measure / metrics.orphan_ratio / metrics.max_topic_depth
    누락/None/비수치 키는 0으로 안전 처리(구버전 스냅샷·0쌍에도 죽지 않음).
    """
    sem = snapshot.get("semantic") or {}
    met = snapshot.get("metrics") or {}

    def _num(x) -> float:
        return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else 0.0

    coverage = _num(sem.get("coverage_ratio"))
    purity = _num((sem.get("tag_purity_topic") or {}).get("purity_weighted"))
    vmeasure = _num((sem.get("v_measure_topic") or {}).get("v_measure"))
    orphan = _num(met.get("orphan_ratio"))
    depth = _num(met.get("max_topic_depth"))

    depth_score = 1.0 if depth <= _DEPTH_OK else max(0.0, 1.0 - (depth - _DEPTH_OK) / 6.0)
    w = OBJECTIVE_WEIGHTS
    j = (w["coverage_ratio"] * coverage
         + w["purity_weighted"] * purity
         + w["v_measure"] * vmeasure
         + w["orphan_ratio"] * (1.0 - orphan)
         + w["depth"] * depth_score)
    return {
        "J": round(j, 4),
        "components": {
            "coverage_ratio": round(coverage, 4),
            "purity_weighted": round(purity, 4),
            "v_measure": round(vmeasure, 4),
            "orphan_ratio": round(orphan, 4),
            "max_topic_depth": depth,
            "depth_score": round(depth_score, 4),
        },
        "weights": dict(w),
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
    if m == 0:
        # 엣지 0 — Louvain modularity가 ZeroDivision. 커뮤니티/중심성은 건너뛴다.
        return {"nodes": n, "edges": 0, "kinds": kinds, **_topic_metrics(g)}

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
        # HIVE-46: 과파편화 직접 측정 구조 지표(orphan_ratio·max_topic_depth·content_per_topic)
        **_topic_metrics(g),
    }
