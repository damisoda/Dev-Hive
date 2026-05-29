# recommend — 추천 엔진 (백엔드 파이프라인 3)

유저 상태를 추적하고 다음 콘텐츠를 추천한다.

## Layer 1 (1차 데모): 룰베이스 v0
- `rule_based.py` — 벡터 유사도(user_vector x content_vector) + 미독 필터 + 난이도 필터

## Layer 2: GraphRAG
- `llm_kt.py` — LLM Knowledge Tracing. 유저 읽음 이력을 자연어 user_state로 직렬화
- `graphrag.py` — Stage A(벡터 검색 top-10 + 룰 필터) + Stage B(Haiku rerank + 근거 생성)

## 추천 응답 포맷
```json
{
  "recommendations": [
    {"content_id": 42, "score": 0.9, "reason": "..."},
    ...
  ]
}
```
