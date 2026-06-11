# tagging — AI 태깅 + 가공 + 임베딩 (백엔드 파이프라인 1)

크롤링된 콘텐츠를 QC 게이트로 거르고, LLM으로 태깅·가공한 뒤 임베딩을 생성하여 DB에 적재한다.

## 구성
- `haiku_tagging_prompt.md` — Claude Haiku 태깅 프롬프트
- `tagger.py` — Claude Haiku 태깅 (7개 대주제 relevance + 난이도 + quality_score + content_type)
- `synthesizer.py` — **가공(synthesis, HIVE-41)**. content_type 5타입(experience / tutorial / concept / tool / discussion)별 카드(공통헤더 + 타입별 바디) 생성. raw 재게시·환각 금지, 실패 시 None(graceful)
- `embedder.py` — OpenAI text-embedding-3-small 임베딩 생성 (1536차원, **원문 고정** — 가공본은 임베딩하지 않음)
- `loader.py` — content + content_node_mapping 적재 (relevance >= 0.5인 노드에 매핑)
- `ingest.py` — 적재 코어. **QC 게이트 → 배치 태깅(Anthropic Batches) → 가공 → 임베딩 → 건별 트랜잭션 적재**. CLI(`scripts/run_tagging_pipeline.py`)와 스케줄 크롤(`run_crawler.run_pipeline`)이 공유. `--batch-id` 재접속 지원

가공 카드는 `content.synthesis`(JSONB)에 별도 저장된다. 크롤 적재 시점 전량 가공 대신,
추천으로 노출이 확정될 때 lazy 생성하는 경로도 있다(`app/services/lazy_synthesis.py`, HIVE-49).
유저 업로드(HIVE-33)는 즉시 피드백을 위해 eager 가공한다.

## 파이프라인 실행

```bash
cd backend
python scripts/run_tagging_pipeline.py data/raw/velog_20260610.json
python scripts/run_tagging_pipeline.py data/raw/x_20260610.json --limit 50
```

필요 환경변수: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DATABASE_URL`

## 태깅 출력 포맷
```json
{
  "relevance": {"프롬프트 엔지니어링": 0.8, "Agentic AI": 0.2, ...},
  "difficulty": "중급",
  "quality_score": 0.85,
  "content_type": "experience",
  "language": "ko"
}
```

quality_score < 0.5인 콘텐츠는 적재하지 않는다.
