# graph — 그래프 + 학습 (백엔드 파이프라인 2)

**Layer 2 작업.** 1차 데모(5/31)에는 포함되지 않는다.

## 구성 (예정)
- `builder.py` — Content-Author-Tag-CurriculumNode-Source 이종 그래프 구축
- `auto_hkg.py` — LLM 그래프 적합도 판단 + 하위 노드 자동 생성
- `sage_export.py` — GraphSAGE 학습 임베딩을 content.graph_embedding에 적재

## GraphSAGE 학습
학습 자체는 `training/` 폴더의 Colab 노트북에서 수행한다.
산출된 노드 임베딩(256차원)을 pgvector에 적재하여 추천 retrieval에 활용.
