"""HIVE-20 (C): Colab 학습 산출 임베딩(.npz) → content.graph_embedding 적재 (로컬).

graphsage_train.ipynb가 만든 embeddings.npz {content_ids, graph_emb[N,256]}를 읽어
content.graph_embedding(vector(256))에 UPDATE한다. id 정합성 검증 + idempotent.
--dry-run으로 커밋 없이 검증 가능.

실행: cd backend && PYTHONPATH=. venv/bin/python -m app.graph.sage_export --in embeddings.npz [--dry-run]
"""
from __future__ import annotations

import argparse

import numpy as np
from sqlalchemy import text

from app.database import SessionLocal

EMBED_DIM = 256


def load_embeddings(npz_path: str, dry_run: bool = False) -> dict:
    data = np.load(npz_path)
    ids = data["content_ids"].astype(int)
    emb = np.asarray(data["graph_emb"], dtype=float)
    if emb.shape[0] != len(ids):
        raise ValueError(f"행 수 불일치: ids {len(ids)} vs emb {emb.shape[0]}")
    if emb.ndim != 2 or emb.shape[1] != EMBED_DIM:
        raise ValueError(f"임베딩 형태 {emb.shape} — (N, {EMBED_DIM}) 이어야 함")

    db = SessionLocal()
    try:
        existing = {r.id for r in db.execute(text("SELECT id FROM content")).fetchall()}
        updated = skipped = 0
        for cid, vec in zip(ids, emb):
            if int(cid) not in existing:
                skipped += 1  # export 이후 삭제/리시드된 id → 건너뜀
                continue
            vec_str = "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
            db.execute(
                text("UPDATE content SET graph_embedding = (:v)::vector WHERE id = :id"),
                {"v": vec_str, "id": int(cid)},
            )
            updated += 1
        db.rollback() if dry_run else db.commit()
        return {"updated": updated, "skipped_missing_id": skipped, "dry_run": dry_run}
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="GraphSAGE 임베딩 → content.graph_embedding 적재")
    ap.add_argument("--in", dest="inp", default="embeddings.npz")
    ap.add_argument("--dry-run", action="store_true", help="커밋 없이 검증만(롤백)")
    args = ap.parse_args()
    print("적재 결과:", load_embeddings(args.inp, dry_run=args.dry_run))
