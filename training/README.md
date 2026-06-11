# training — GraphSAGE 학습

## 구성
- `graphsage_train.ipynb` — Colab(GPU)용 노트북. DB export(.npz)를 받아 PyTorch Geometric으로 이종 그래프 자기지도학습
- **로컬 학습 스크립트 `backend/scripts/train_graphsage_local.py`** — 노트북(셀 2~7)과 동일 로직.
  현재 그래프 규모(노드 ~1k, full-batch 200 epoch)는 CPU 수 초면 끝나 Colab 왕복이 오히려 비싸다.
  평소 재학습(예: precedes 추가 후)은 이 스크립트가 기본 경로다.

## 전체 파이프라인 (로컬)
```bash
cd backend
PYTHONPATH=. venv/bin/python -m app.graph.export_graph --out data/graph_export.npz
venv/bin/python scripts/train_graphsage_local.py            # data/embeddings.npz 생성
PYTHONPATH=. venv/bin/python -m app.graph.sage_export --in data/embeddings.npz --dry-run
PYTHONPATH=. venv/bin/python -m app.graph.sage_export --in data/embeddings.npz
```

## 학습 설계
- 입력 피처: content = text_embedding(1536), topic = 소속 콘텐츠 임베딩 centroid
- 모델: proj → SAGEConv×2 → L2 정규화 (256차원, 코사인 친화)
- 링크 예측 타깃: **구조 신호만(belongs_to + precedes)**. similar_to는 텍스트 임베딩 파생이라 타깃에 넣으면 순환이 생겨 제외

## 산출물 (실측 2026-06-11, 994 content · 33 topic)
- 학습 시간: CPU 약 7초, val link-AUC 0.768
- 노드 임베딩 256차원 → `content.graph_embedding`에 994/994건 적재

## 의존성 (requirements에 없음 — 학습 시에만 설치)
```
torch
torch-geometric
scikit-learn
```
