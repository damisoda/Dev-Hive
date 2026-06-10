"""HIVE-46 평가 지표 단위 테스트.

- _topic_metrics: 과파편화 구조 지표(orphan_ratio·max_topic_depth·content_per_topic)
- cluster_quality: 임베딩 클러스터 품질(cohesion·separation·silhouette)
- compute_metrics: m==0(엣지 0) 가드 — Louvain ZeroDivision 방지
"""
import networkx as nx
import numpy as np

from app.graph.metrics import (
    _topic_metrics,
    cluster_label_purity,
    cluster_quality,
    compute_metrics,
    label_cluster_agreement,
)


def _topic(g, nid, parent, auto):
    g.add_node(f"topic:{nid}", kind="topic", node_id=nid, parent_id=parent, auto=auto)


def _content(g, cid, topic_nid):
    g.add_node(f"content:{cid}", kind="content", content_id=cid)
    g.add_edge(f"content:{cid}", f"topic:{topic_nid}", rel="belongs_to", weight=1.0)


# ── _topic_metrics ─────────────────────────────────────────────────────────

def test_topic_metrics_orphan_depth_and_counts():
    g = nx.MultiDiGraph()
    _topic(g, 1, None, False)     # 대주제(root)
    _topic(g, 100, 1, True)       # auto, depth1, 콘텐츠 3 → 정상
    _topic(g, 101, 1, True)       # auto, depth1, 콘텐츠 1 → 고아
    _topic(g, 102, 100, True)     # auto, depth2(중첩), 콘텐츠 2
    for c in (10, 11, 12):
        _content(g, c, 100)
    _content(g, 20, 101)
    _content(g, 30, 102)
    _content(g, 31, 102)

    m = _topic_metrics(g)
    assert m["auto_topics"] == 3
    assert m["orphan_ratio"] == round(1 / 3, 4)   # 101만 고아
    assert m["max_topic_depth"] == 2              # 102: 1←100←(102) 체인
    assert m["content_per_auto_topic"] == {"mean": 2.0, "median": 2, "min": 1, "max": 3}


def test_topic_metrics_no_auto_nodes():
    g = nx.MultiDiGraph()
    _topic(g, 1, None, False)
    _content(g, 10, 1)
    m = _topic_metrics(g)
    assert m["auto_topics"] == 0 and m["orphan_ratio"] == 0.0 and m["max_topic_depth"] == 0


# ── cluster_quality ────────────────────────────────────────────────────────

def test_cluster_quality_two_tight_clusters():
    embs = {
        1: [np.array([1.0, 0, 0, 0])] * 3,   # 동일 방향 → 응집 1.0
        2: [np.array([0, 1.0, 0, 0])] * 3,   # 직교 → 분리 0
    }
    q = cluster_quality(embs)
    assert q["n_clusters"] == 2 and q["n_points"] == 6
    assert q["cohesion"] == 1.0
    assert q["separation"] == 0.0
    assert q["silhouette"] == 1.0   # intra 0, inter 1


def test_cluster_quality_single_cluster_no_separation():
    q = cluster_quality({1: [np.array([1.0, 0, 0]), np.array([0.9, 0.1, 0])]})
    assert q["n_clusters"] == 1
    assert q["separation"] is None and q["silhouette"] is None
    assert q["cohesion"] is not None


def test_cluster_quality_ignores_singletons():
    # 멤버 1개 클러스터는 품질평가 제외 → 유효 클러스터 0
    q = cluster_quality({1: [np.array([1.0, 0])], 2: [np.array([0, 1.0])]})
    assert q["n_clusters"] == 0 and q["cohesion"] is None


# ── cluster_label_purity ───────────────────────────────────────────────────

def test_cluster_label_purity_fully_homogeneous():
    # 각 클러스터가 단일 라벨 → 순도 1.0. baseline=전체 최빈비(4/6).
    p = cluster_label_purity({1: ["a", "a", "a"], 2: ["b", "b"], 3: ["a"]})
    assert p["n_clusters"] == 3
    assert p["purity_mean"] == 1.0
    assert p["purity_weighted"] == 1.0
    assert p["baseline"] == round(4 / 6, 4)   # a가 4건/총 6건


def test_cluster_label_purity_mixed_fraction():
    # c1: a 2/3 (최빈 2), c2: 단일. mean=(2/3+1)/2, weighted=(2+2)/5.
    p = cluster_label_purity({1: ["a", "a", "b"], 2: ["b", "b"]})
    assert p["purity_mean"] == round((2 / 3 + 1.0) / 2, 4)
    assert p["purity_weighted"] == round(4 / 5, 4)   # 최빈합 4 / 총 5
    # 전체 b가 3건/5건 → baseline 0.6
    assert p["baseline"] == 0.6


def test_cluster_label_purity_ignores_none():
    # None은 무시 — c1은 ["a"]만 남아 순도 1.0, 빈 클러스터(c2)는 카운트 제외.
    p = cluster_label_purity({1: ["a", None], 2: [None, None]})
    assert p["n_clusters"] == 1
    assert p["purity_mean"] == 1.0
    assert p["baseline"] == 1.0      # 유효 라벨이 "a" 하나뿐


def test_cluster_label_purity_empty():
    assert cluster_label_purity({}) == {
        "n_clusters": 0, "purity_mean": None, "purity_weighted": None, "baseline": None
    }
    # 전부 None인 경우도 빈 것과 동일
    assert cluster_label_purity({1: [None, None]})["n_clusters"] == 0


# ── label_cluster_agreement (V-measure) ───────────────────────────────────

def test_v_measure_perfect():
    # 클러스터 == 클래스 → V=1.0
    r = label_cluster_agreement(["a", "a", "b", "b", "c"], [1, 1, 2, 2, 3])
    assert r["v_measure"] == 1.0 and r["homogeneity"] == 1.0 and r["completeness"] == 1.0


def test_v_measure_matches_sklearn():
    from sklearn.metrics import homogeneity_completeness_v_measure
    true = ["a", "a", "b", "a", "b", "c", "c", "a"]
    pred = [1, 1, 1, 2, 2, 2, 3, 3]
    r = label_cluster_agreement(true, pred)
    h, c, v = homogeneity_completeness_v_measure(true, pred)
    assert abs(r["v_measure"] - round(v, 4)) < 1e-3
    assert abs(r["homogeneity"] - round(h, 4)) < 1e-3
    assert abs(r["completeness"] - round(c, 4)) < 1e-3


def test_v_measure_ignores_none_and_empty():
    assert label_cluster_agreement([None, None], [1, 2])["n"] == 0
    r = label_cluster_agreement(["a", "a", None], [1, 1, 2])
    assert r["n"] == 2  # None 항목 제외


# ── compute_metrics m==0 가드 ──────────────────────────────────────────────

def test_compute_metrics_no_edges_does_not_crash():
    g = nx.MultiDiGraph()
    _topic(g, 1, None, False)
    _topic(g, 2, 1, True)         # 엣지 없음(belongs_to 0)
    m = compute_metrics(g)        # Louvain ZeroDivision 없이 반환되어야
    assert m["nodes"] == 2 and m["edges"] == 0
    assert "orphan_ratio" in m    # 구조 지표는 포함
