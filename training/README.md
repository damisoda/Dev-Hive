# training — GraphSAGE 학습

**Layer 2 작업.** Google Colab 무료 티어(T4 GPU)에서 수행한다.

## 구성 (예정)
- `graphsage_train.ipynb` — Colab 노트북
  - DB에서 그래프 데이터 로드 (Content-Author-Tag-CurriculumNode-Source)
  - PyTorch Geometric으로 이종 그래프 구성
  - 자기지도학습 (link prediction + contrastive loss)
  - 노드 임베딩(256차원) 산출 → DB content.graph_embedding에 적재

## 산출물
- 학습된 노드 임베딩
- 학습 곡선, link prediction AUC (발표 자료용)
- t-SNE 임베딩 시각화

## 의존성 (Colab에서 설치)
```
torch
torch-geometric
psycopg2-binary
pgvector
```
