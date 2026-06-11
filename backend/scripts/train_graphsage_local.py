"""HIVE-20 후속: GraphSAGE 로컬 학습 — Colab 없이 한 줄로 재학습.

training/graphsage_train.ipynb(셀 2~7)와 동일 로직의 스크립트판. 이 그래프 규모
(노드 ~1k, full-batch 200 epoch)는 CPU로 수 초면 끝나 Colab 왕복이 오히려 비싸다.
노트북은 Colab(GPU)용으로 유지하고, 평소 재학습(예: precedes 추가 후)은 이걸 쓴다.

전체 파이프라인:
    cd backend
    PYTHONPATH=. venv/bin/python -m app.graph.export_graph --out data/graph_export.npz
    venv/bin/python scripts/train_graphsage_local.py            # data/embeddings.npz 생성
    PYTHONPATH=. venv/bin/python -m app.graph.sage_export --in data/embeddings.npz --dry-run
    PYTHONPATH=. venv/bin/python -m app.graph.sage_export --in data/embeddings.npz

의존성: torch, torch-geometric, scikit-learn (requirements에 없음 — 학습 시에만 설치).
실측(2026-06-11, 994 content·33 topic): 7초, val link-AUC 0.768.
"""
from __future__ import annotations

import argparse
import time

import numpy as np
import torch
import torch.nn.functional as F
from sklearn.metrics import roc_auc_score
from torch_geometric.data import Data
from torch_geometric.nn import SAGEConv
from torch_geometric.utils import negative_sampling


class GraphSAGE(torch.nn.Module):
    """노트북과 동일: proj → SAGE×2 → L2 정규화(코사인 친화)."""

    def __init__(self, in_dim: int, hid: int = 256, out: int = 256):
        super().__init__()
        self.proj = torch.nn.Linear(in_dim, hid)
        self.conv1 = SAGEConv(hid, hid)
        self.conv2 = SAGEConv(hid, out)
        self.drop = torch.nn.Dropout(0.3)

    def forward(self, x, edge_index):
        h = F.relu(self.proj(x))
        h = self.drop(F.relu(self.conv1(h, edge_index)))
        h = self.conv2(h, edge_index)
        return F.normalize(h, p=2, dim=1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="data/graph_export.npz",
                    help="export_graph 산출물 경로")
    ap.add_argument("--out", default="data/embeddings.npz",
                    help="sage_export 입력이 될 임베딩 경로")
    ap.add_argument("--epochs", type=int, default=200)
    ap.add_argument("--seed", type=int, default=42, help="train/val 분할 재현용")
    args = ap.parse_args()

    t0 = time.time()
    d = np.load(args.inp)
    feat_dim = int(d["meta"][0])
    n_content, n_topic = len(d["content_ids"]), len(d["topic_ids"])
    print("content", n_content, "topic", n_topic, "feat_dim", feat_dim,
          "| belongs_to", len(d["belongs_to"]), "similar_to", len(d["similar_to"]),
          "precedes", len(d["precedes"]))

    # 노드: content[0..n_content-1] 다음에 topic[n_content..]. 피처는 같은 공간.
    x = torch.tensor(np.vstack([d["content_feat"], d["topic_feat"]]), dtype=torch.float)

    def to_edge(arr, src_topic=False, dst_topic=False):
        if len(arr) == 0:
            return torch.empty((2, 0), dtype=torch.long)
        s = arr[:, 0].astype(int) + (n_content if src_topic else 0)
        t = arr[:, 1].astype(int) + (n_content if dst_topic else 0)
        return torch.tensor(np.vstack([s, t]), dtype=torch.long)

    bt = to_edge(d["belongs_to"], dst_topic=True)                 # content -> topic
    st_ = to_edge(d["similar_to"])                                # content -> content
    pr = to_edge(d["precedes"], src_topic=True, dst_topic=True)   # topic -> topic

    # 메시지 패싱 엣지 = 전부 + 역방향(무방향화)
    mp = torch.cat([bt, st_, pr], dim=1)
    mp = torch.cat([mp, mp.flip(0)], dim=1)
    data = Data(x=x, edge_index=mp, num_nodes=x.size(0))

    # 링크 예측 타깃: 구조 신호만(belongs_to + precedes). similar_to(=text 파생)는
    # 제외해 순환 차단(피처가 text_embedding이라 타깃까지 text면 자기복제 학습).
    pos = torch.cat([bt, pr], dim=1)
    torch.manual_seed(args.seed)
    perm = torch.randperm(pos.size(1))
    n_val = max(1, int(0.1 * pos.size(1)))
    val_pos, train_pos = pos[:, perm[:n_val]], pos[:, perm[n_val:]]
    print("link-pred positives:", pos.size(1),
          "(train", train_pos.size(1), "/ val", n_val, ")")

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    model = GraphSAGE(feat_dim).to(dev)
    data = data.to(dev)
    opt = torch.optim.Adam(model.parameters(), lr=0.01, weight_decay=5e-4)

    def link_loss(z, pos_edges):
        neg = negative_sampling(pos_edges, num_nodes=z.size(0),
                                num_neg_samples=pos_edges.size(1))
        pos_s = (z[pos_edges[0]] * z[pos_edges[1]]).sum(-1)
        neg_s = (z[neg[0]] * z[neg[1]]).sum(-1)
        s = torch.cat([pos_s, neg_s])
        y = torch.cat([torch.ones_like(pos_s), torch.zeros_like(neg_s)])
        return F.binary_cross_entropy_with_logits(s, y), s, y

    tp, vp = train_pos.to(dev), val_pos.to(dev)
    for ep in range(1, args.epochs + 1):
        model.train()
        opt.zero_grad()
        z = model(data.x, data.edge_index)
        loss, _, _ = link_loss(z, tp)
        loss.backward()
        opt.step()
        if ep % 40 == 0 or ep == args.epochs:
            model.eval()
            with torch.no_grad():
                z = model(data.x, data.edge_index)
                _, s, y = link_loss(z, vp)
                auc = roc_auc_score(y.cpu().numpy(), torch.sigmoid(s).cpu().numpy())
            print(f"epoch {ep:3d} | loss {loss.item():.4f} | val link-AUC {auc:.3f}")

    # content 노드 임베딩만 추출 → sage_export 입력 포맷
    model.eval()
    with torch.no_grad():
        z = model(data.x, data.edge_index).cpu().numpy()
    graph_emb = z[:n_content].astype("float32")
    np.savez(args.out, content_ids=d["content_ids"], graph_emb=graph_emb)
    print(f"saved {args.out} {graph_emb.shape} | 총 {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
