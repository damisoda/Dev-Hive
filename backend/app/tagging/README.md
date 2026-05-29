# tagging — AI 태깅 + 임베딩 (백엔드 파이프라인 1)

크롤링된 콘텐츠를 LLM으로 태깅하고 임베딩을 생성하여 DB에 적재한다.

## 구성 (예정)
- `tagger.py` — Claude Haiku 태깅 (7개 대주제 relevance + 난이도 + quality_score + content_type)
- `embedder.py` — OpenAI text-embedding-3-small 임베딩 생성
- `loader.py` — content + content_node_mapping 적재 (relevance >= 0.5인 노드에 매핑)

## 태깅 출력 포맷
```json
{
  "topics": {"프롬프트 엔지니어링": 0.8, "Agentic AI": 0.2, ...},
  "difficulty": "중급",
  "quality_score": 0.85,
  "content_type": "experience",
  "language": "ko"
}
```

quality_score < 0.5인 콘텐츠는 적재하지 않는다.
