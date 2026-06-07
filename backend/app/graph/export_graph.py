"""HIVE-20 (A): 그래프 → GraphSAGE 학습용 .npz export (로컬 실행).

Colab은 로컬 DB(localhost)에 닿지 못하므로, 학습 입력을 이 스크립트로 .npz에 떨궈
Colab 노트북(training/graphsage_train.ipynb)에 업로드해 쓴다. torch/PyG 불필요 — numpy만.

내용:
- content_ids / content_feat : 콘텐츠 노드 id, 피처(=text_embedding 그대로; feat_dim은 meta에)
- topic_ids   / topic_feat   : 커리큘럼 노드 id, 피처(=소속 content 임베딩 centroid, 없으면 0)
- belongs_to / similar_to / precedes : (src_idx, dst_idx, weight) — 노드는 0-based 로컬 인덱스
- meta : [feat_dim]

실행: cd backend && PYTHONPATH=. venv/bin/python -m app.graph.export_graph --out data/graph_export.npz
"""
from __future__ import annotations

import argparse
import os
from collections import defaultdict

import numpy as np
from sqlalchemy import text

from app.database import SessionLocal
from app.graph.builder import build_graph


def _parse_vec(raw) -> np.ndarray | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        vals = [v for v in raw.strip("[]").split(",") if v.strip()]
        return np.array([float(x) for x in vals], dtype=np.float32) if vals else None
    return np.array([float(x) for x in raw], dtype=np.float32)


def export_graph(out_path: str) -> dict:
    db = SessionLocal()
    try:
        # content 피처(text_embedding)
        rows = db.execute(
            text("SELECT id, text_embedding::text AS emb FROM content WHERE text_embedding IS NOT NULL")
        ).fetchall()
        content_emb = {r.id: v for r in rows if (v := _parse_vec(r.emb)) is not None}
        if not content_emb:
            raise RuntimeError("text_embedding이 있는 content가 없습니다 — export 불가")
        feat_dim = len(next(iter(content_emb.values())))

        # topic centroid = 소속 content 임베딩 평균 (belongs_to 기반)
        members: dict[int, list] = defaultdict(list)
        for r in db.execute(text("SELECT content_id, node_id FROM content_node_mapping")).fetchall():
            if r.content_id in content_emb:
                members[r.node_id].append(content_emb[r.content_id])
        topic_ids = [r.id for r in db.execute(text("SELECT id FROM curriculum_nodes ORDER BY id")).fetchall()]

        # 노드 0-based 인덱스
        content_ids = list(content_emb.keys())
        cidx = {cid: i for i, cid in enumerate(content_ids)}
        tidx = {tid: i for i, tid in enumerate(topic_ids)}
        content_feat = np.stack([content_emb[c] for c in content_ids])
        topic_feat = (
            np.stack([
                np.mean(members[t], axis=0) if members.get(t) else np.zeros(feat_dim, np.float32)
                for t in topic_ids
            ]) if topic_ids else np.zeros((0, feat_dim), np.float32)
        )

        # 엣지: build_graph(HIVE-19)로 belongs_to/similar_to/precedes 추출
        g = build_graph(db)
        edges: dict[str, list] = {"belongs_to": [], "similar_to": [], "precedes": []}
        for u, v, d in g.edges(data=True):
            rel, w = d.get("rel"), float(d.get("weight", 0.0))
            ku, iu = u.split(":"); kv, iv = v.split(":")
            iu, iv = int(iu), int(iv)
            if rel == "belongs_to" and iu in cidx and iv in tidx:
                edges["belongs_to"].append((cidx[iu], tidx[iv], w))
            elif rel == "similar_to" and iu in cidx and iv in cidx:
                edges["similar_to"].append((cidx[iu], cidx[iv], w))
            elif rel == "precedes" and iu in tidx and iv in tidx:
                edges["precedes"].append((tidx[iu], tidx[iv], w))

        def _arr(lst):
            return np.array(lst, dtype=np.float32).reshape(-1, 3) if lst else np.zeros((0, 3), np.float32)

        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        np.savez(
            out_path,
            content_ids=np.array(content_ids, dtype=np.int64),
            content_feat=content_feat,
            topic_ids=np.array(topic_ids, dtype=np.int64),
            topic_feat=topic_feat,
            belongs_to=_arr(edges["belongs_to"]),
            similar_to=_arr(edges["similar_to"]),
            precedes=_arr(edges["precedes"]),
            meta=np.array([feat_dim], dtype=np.int64),
        )
        return {
            "content": len(content_ids), "topic": len(topic_ids), "feat_dim": feat_dim,
            **{k: len(v) for k, v in edges.items()}, "out": out_path,
        }
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="그래프 → GraphSAGE 학습용 .npz export")
    ap.add_argument("--out", default="data/graph_export.npz")
    args = ap.parse_args()
    print("export 완료:", export_graph(args.out))
