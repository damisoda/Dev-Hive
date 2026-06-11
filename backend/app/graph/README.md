# graph — 그래프 + 학습 (백엔드 파이프라인 2)

## 구성 (구현됨)
- `builder.py` — DB(curriculum_nodes · content · content_node_mapping · node_links)를 networkx 이종 그래프로 로드. 노드 2종(topic / content) + 엣지 3종(belongs_to / similar_to / precedes). similar_to는 저장하지 않고 빌드 시 pgvector top-5로 도출
- `auto_hkg.py` — **Auto-HKG v2 (2패스, HIVE-44)**. v1의 per-content 그리디 매칭(자동노드 825개·94% 고아)을 폐기하고: 1패스 대주제 흡수(코사인 ≥ 0.70) → 2패스 잔여 클러스터링(코사인 ≥ 0.65, MIN 3 연결요소) → 승격 클러스터만 Haiku로 네이밍. 실측(994건): 자동노드 26개 · orphan 0 · depth 1
- `export_graph.py` — 그래프 → GraphSAGE 학습 입력 `.npz` export (numpy만 사용)
- `sage_export.py` — 학습 산출 임베딩(`embeddings.npz`) → `content.graph_embedding`(vector(256)) 적재. id 정합성 검증 + idempotent + `--dry-run` 지원
- `metrics.py` — 자기조직화 정량 지표 (modularity, ADC, 허브/브릿지, LCC 등, HIVE-38)

## GraphSAGE 학습
기본 경로는 **로컬 학습 스크립트** `backend/scripts/train_graphsage_local.py`다
(이 그래프 규모는 CPU 7초면 충분 — 실측 2026-06-11, 994 content·33 topic, val link-AUC 0.768).
Colab 노트북(`training/graphsage_train.ipynb`)은 GPU용으로 유지한다.

```bash
cd backend
PYTHONPATH=. venv/bin/python -m app.graph.export_graph --out data/graph_export.npz
venv/bin/python scripts/train_graphsage_local.py            # data/embeddings.npz 생성
PYTHONPATH=. venv/bin/python -m app.graph.sage_export --in data/embeddings.npz
```

링크 예측 타깃은 구조 신호(belongs_to + precedes)만 사용한다 —
similar_to는 텍스트 임베딩 파생이라 타깃에 넣으면 순환(텍스트→그래프→텍스트)이 생긴다.
산출된 256차원 임베딩은 994/994건 전량 적재되어 추천 retrieval에 활용된다.
