-- 데모용 시드 데이터 25건
-- 대주제 7종 + 소스 6종 + 난이도 3단계 + 한/영 혼합
-- 적용: psql -d devhive -f demo_seed.sql
--      또는 docker compose 내부에서: docker exec -i devhive-db psql -U devhive -d devhive < demo_seed.sql
--
-- 주의: text_embedding은 NULL로 들어감. 진하의 임베딩 스크립트(HIVE-11)가 채워야 함.
-- 임시로 룰베이스 추천을 quality_score 정렬로 운영하면 임베딩 없이도 데모 가능.

-- ============================================
-- CONTENT INSERTS
-- ============================================

INSERT INTO content (title, body, url, source, author_name, language, difficulty, quality_score, content_type, tags, engagement_likes, engagement_comments, published_at) VALUES

-- ===== 프롬프트 엔지니어링 =====
(
  'Claude XML 태그로 출력 포맷 강제하는 패턴 정리',
  '6개월간 Claude로 자동화 만들면서 발견한 가장 강력한 패턴: XML 태그를 시스템 프롬프트에 넣으면 출력 일관성이 90% 이상 올라간다. <output_format> 태그 안에 원하는 구조를 정의하고, <example> 태그로 1-2개 예시를 주면 Claude가 거의 100% 그대로 따라온다. JSON 응답이 깨질 일이 사라졌다. few-shot보다 효과적이었던 이유는 Claude가 XML 학습에 특화되어 있기 때문이라고 추측한다.',
  'https://velog.io/@skysoo/Claude-Code-%EC%99%84%EB%B2%BD-%EA%B0%80%EC%9D%B4%EB%93%9C-%ED%95%9C%EA%B8%80-%EC%9A%94%EC%95%BD%EB%B3%B8',
  'reddit', 'prompt_master_92', 'ko', '중급', 0.92, 'experience',
  '["Claude", "프롬프트 엔지니어링", "XML", "few-shot"]',
  342, 67, '2026-05-25 14:23:00+09'
),
(
  'Chain of Thought 프롬프트의 실제 효과 비교 - 3개월 측정 결과',
  'GPT-5와 Claude Opus 4.7에서 CoT 프롬프트의 효과를 정량 측정. 단순 산수 문제는 5% 개선, 다단계 추론은 23% 개선, 코드 디버깅은 31% 개선. 단 CoT를 강제하면 응답 시간이 1.8배 늘어남. 결론: 복잡한 추론 작업에만 선택적 사용 권고.',
  'https://news.ycombinator.com/item?id=42560558',
  'hn', 'ml_engineer_22', 'en', '고급', 0.88, 'discussion',
  '["CoT", "프롬프트 엔지니어링", "벤치마크"]',
  187, 94, '2026-05-23 09:15:00+09'
),
(
  '초보자를 위한 ChatGPT 프롬프트 기초 - 5가지 원칙',
  '비개발자 친구들에게 알려준 5가지 원칙: 1) 역할 부여 2) 출력 형식 명시 3) 예시 제공 4) 단계별 지시 5) 제약 조건 명시. 이거 5개만 지켜도 결과가 완전히 달라진다는 걸 보여줬더니 다들 ChatGPT 헤비유저가 됨.',
  'https://velog.io/@rollingman1/Claude-AI-%EB%AC%B4%EB%A3%8C%EB%A1%9C-pdf%EB%A1%9C-%EB%8C%80%ED%99%94%ED%95%98%EA%B8%B0.-ChatGPT-Pro-%ED%95%84%EC%9A%94%EC%97%86%EC%96%B4%EC%9A%94',
  'velog', 'beginner_ai', 'ko', '입문', 0.78, 'tutorial',
  '["ChatGPT", "프롬프트 엔지니어링", "입문"]',
  89, 23, '2026-05-22 16:40:00+09'
),

-- ===== Agentic AI =====
(
  'MCP 서버 5개 연동해서 풀자동 코드리뷰 봇 만들어봤다',
  'GitHub MCP + Linear MCP + Slack MCP + Filesystem MCP + Custom DB MCP를 Claude Code Agent에 물려서 PR 자동 리뷰 → Linear 이슈 생성 → Slack 알림까지 한 번에 처리. 핵심 인사이트: MCP 5개 동시 사용 시 컨텍스트 윈도우 60% 차서 toolset 동적 로딩이 필수. 코드와 셋업 가이드 첨부.',
  'https://velog.io/@windowook/Claude-Code-ContextEngineering',
  'reddit', 'agent_builder', 'en', '고급', 0.94, 'experience',
  '["MCP", "Claude Code", "Agentic AI", "오케스트레이션"]',
  512, 134, '2026-05-26 11:30:00+09'
),
(
  'LangGraph vs CrewAI vs AutoGen 실전 비교 (2026년 5월 기준)',
  '세 프레임워크로 같은 멀티에이전트 시스템을 만들어 비교: LangGraph는 상태 관리 강력하지만 학습 곡선 가파름, CrewAI는 셋업 빠르지만 복잡한 흐름 어려움, AutoGen은 대화형 에이전트에 강함. 결론은 LangGraph 추천.',
  'https://news.ycombinator.com/item?id=47000034',
  'hn', 'multi_agent_dev', 'en', '고급', 0.91, 'discussion',
  '["LangGraph", "CrewAI", "AutoGen", "Agentic AI", "비교"]',
  234, 78, '2026-05-24 13:20:00+09'
),
(
  'MCP 입문: Claude Desktop에 SQLite 연결하기 5분 가이드',
  'MCP가 뭔지 처음 듣는 사람을 위한 가장 쉬운 시작. SQLite MCP 서버 설치 → Claude Desktop config 수정 → 자연어로 DB 조회까지 5분. 스크린샷 7장으로 단계별 설명.',
  'https://velog.io/@strurao/Claude-Code%EC%9D%98-%EA%B5%AC%EC%A1%B0-%EC%84%A4%EA%B3%84-%ED%95%98%EB%84%A4%EC%8A%A4%EB%8A%94-%EC%96%87%EA%B2%8C-%EC%A7%80%EB%8A%A5%EC%9D%80-%EB%AA%A8%EB%8D%B8%EC%97%90',
  'tistory', 'tech_newbie', 'ko', '입문', 0.82, 'tutorial',
  '["MCP", "Claude Desktop", "SQLite", "입문"]',
  156, 41, '2026-05-21 19:55:00+09'
),

-- ===== 멀티모달 AI =====
(
  'Sora 2.0 비디오 생성 한계 테스트 - 30개 프롬프트 결과',
  'Sora 2.0으로 다양한 시나리오 생성: 일상 장면 90% 만족, 복잡한 액션 60%, 다중 인물 상호작용 40%. 가장 잘 되는 패턴은 단일 주제 + 명확한 카메라 무브먼트. 워터마크 제거 정책으로 상업 사용 제약 있음 주의.',
  'https://huggingface.co/blog/saumitras/colpali-milvus-multimodal-rag',
  'reddit', 'video_gen_pro', 'en', '중급', 0.85, 'experience',
  '["Sora", "비디오 생성", "멀티모달", "OpenAI"]',
  423, 102, '2026-05-25 22:10:00+09'
),
(
  'Flux와 SDXL Lightning 비교 - 어떤 이미지 모델 골라야 하나',
  '실무에서 두 모델 6개월간 병행 사용한 결과 정리. Flux는 사진 사실성에 강하고 SDXL Lightning은 일러스트/디자인에 강함. 비용은 Flux가 1.5배. 결론: 용도별 분기 운영 권고.',
  'https://huggingface.co/blog/Omartificial-Intelligence-Space/building-multimodal-rag-systems',
  'velog', 'designer_dev', 'ko', '중급', 0.83, 'experience',
  '["Flux", "SDXL", "이미지 생성", "멀티모달"]',
  201, 56, '2026-05-23 10:30:00+09'
),
(
  'Multimodal RAG: 이미지와 텍스트를 동시에 검색하는 시스템 만들기',
  'CLIP 임베딩 + pgvector + Anthropic Vision API로 멀티모달 RAG 구축. 5만 장 이미지 + 텍스트 문서를 함께 인덱싱했고 검색 속도는 200ms 이내 유지. 아키텍처 다이어그램 첨부.',
  'https://huggingface.co/learn/cookbook/en/multimodal_rag_using_document_retrieval_and_vlms',
  'huggingface', 'mm_researcher', 'en', '고급', 0.93, 'paper',
  '["멀티모달", "RAG", "CLIP", "vector search"]',
  178, 32, '2026-05-22 08:45:00+09'
),

-- ===== RAG & 지식 관리 =====
(
  '사내 위키 5만 페이지 RAG 시스템 6개월 운영기',
  'Notion + Confluence + Google Docs 5만 페이지를 pgvector로 통합. 핵심 교훈: 1) 청킹 전략이 검색 품질의 70% 결정 2) hybrid search(BM25 + 벡터) 필수 3) 메타데이터 필터가 가장 큰 정확도 개선. 비용은 월 $1,200 수준.',
  'https://news.ycombinator.com/item?id=45645349',
  'hn', 'rag_pm', 'en', '고급', 0.95, 'experience',
  '["RAG", "pgvector", "엔터프라이즈", "지식관리"]',
  389, 156, '2026-05-26 07:30:00+09'
),
(
  'Obsidian + Claude 연동으로 개인 지식 베이스 자동 정리',
  '매일 쌓이는 노트를 Claude가 자동으로 태깅하고 연결. Obsidian Plugin + MCP + 자동 백링크 생성으로 검색 시간 80% 단축. 한 달 사용 후기와 설정 파일 공유.',
  'https://velog.io/@softer/Claude-Code-%EC%82%AC%EC%9A%A9-%ED%9A%8C%EA%B3%A0',
  'velog', 'knowledge_worker', 'ko', '중급', 0.87, 'experience',
  '["Obsidian", "Claude", "RAG", "지식관리", "자동화"]',
  267, 78, '2026-05-24 14:00:00+09'
),
(
  'pgvector 튜닝 가이드 - HNSW 인덱스 파라미터 실전',
  'pgvector 0.7+ HNSW 인덱스의 m, ef_construction, ef_search 파라미터를 1000만 벡터 데이터셋에서 그리드서치. 결과: m=32, ef_construction=128, ef_search=64가 latency/recall 균형 최적.',
  'https://github.com/pgvector/pgvector',
  'github_trending', 'pgvector_user', 'en', '고급', 0.90, 'tutorial',
  '["pgvector", "RAG", "벡터 DB", "튜닝"]',
  892, 45, '2026-05-25 11:00:00+09'
),
(
  'RAG 입문: ChatGPT API + LangChain으로 PDF QA 만들기 30분',
  '비전공자도 따라할 수 있는 가장 쉬운 RAG 튜토리얼. PDF 업로드 → 청킹 → 임베딩 → 질문에 답변까지. Python 80줄로 완성. 스크린샷 12장.',
  'https://news.ycombinator.com/item?id=37505687',
  'tistory', 'tutorial_kr', 'ko', '입문', 0.79, 'tutorial',
  '["RAG", "LangChain", "ChatGPT", "PDF", "입문"]',
  445, 89, '2026-05-21 20:15:00+09'
),

-- ===== 오픈소스 AI =====
(
  'Llama 4 70B vs GPT-5 한국어 벤치마크 - 의외의 결과',
  '한국어 작업 50개로 비교: 일반 대화 GPT-5 우세, 코드 생성 동률, 한국 법률/금융 도메인은 Llama 4가 fine-tune 시 더 우수. 로컬에서 돌리는 게 가능해진 시점.',
  'https://www.reddit.com/r/LocalLLaMA/',
  'reddit', 'kr_ml_eng', 'ko', '고급', 0.91, 'discussion',
  '["Llama 4", "GPT-5", "한국어", "오픈소스 AI", "벤치마크"]',
  678, 167, '2026-05-26 15:45:00+09'
),
(
  'Ollama로 Mistral Small 3 띄우고 Cursor에 연결한 후기',
  'M3 Max 64GB에서 Mistral Small 3 (24B) 양자화 버전 돌리고 Cursor에 로컬 LLM endpoint로 연결. 응답 속도 40 tok/s, 코드 품질은 Claude Sonnet의 75% 수준. API 비용 0원.',
  'https://github.com/ollama/ollama',
  'reddit', 'local_dev_mac', 'en', '중급', 0.86, 'experience',
  '["Ollama", "Mistral", "Cursor", "오픈소스 AI", "로컬 LLM"]',
  512, 98, '2026-05-24 12:00:00+09'
),
(
  'vLLM으로 Qwen 2.5 72B 4비트 양자화 서빙 - 처리량 최적화',
  'A100 80GB 4장 클러스터에서 vLLM + AWQ 양자화로 초당 200토큰 처리량 달성. PagedAttention 설정과 dynamic batching 튜닝 가이드. 비용은 클라우드 대비 60% 절감.',
  'https://github.com/vllm-project/vllm',
  'huggingface', 'infra_engineer', 'en', '고급', 0.94, 'tutorial',
  '["vLLM", "Qwen", "양자화", "오픈소스 AI", "서빙"]',
  223, 41, '2026-05-23 09:00:00+09'
),
(
  'HuggingFace Spaces에 무료로 LLM 데모 배포하기',
  'Spaces 무료 티어에서 7B 모델 데모 띄우는 가이드. Gradio UI + ZeroGPU 활용. 코드 100줄로 누구나 자기 모델 공개 가능.',
  'https://huggingface.co/docs/hub/en/spaces-overview',
  'huggingface', 'open_source_dev', 'en', '입문', 0.81, 'tutorial',
  '["HuggingFace", "Spaces", "Gradio", "오픈소스 AI", "입문"]',
  167, 28, '2026-05-22 14:30:00+09'
),

-- ===== AI 워크플로우 & 자동화 =====
(
  'Claude Code로 일주일 동안 PR 47개 머지한 후기',
  '백로그 청소하려고 Claude Code Agent SDK로 자동 리팩터링 파이프라인 짬. 작은 리팩터링 47개를 5일 안에 다 머지. 핵심: 1) 작은 단위 분할 2) 테스트 자동 생성 3) 사람 리뷰는 30초 이내. 시간 절약 40시간.',
  'https://velog.io/@skysoo/Claude-Code-%EC%99%84%EB%B2%BD-%EA%B0%80%EC%9D%B4%EB%93%9C-%ED%95%9C%EA%B8%80-%EC%9A%94%EC%95%BD%EB%B3%B83',
  'reddit', 'productivity_dev', 'en', '중급', 0.93, 'experience',
  '["Claude Code", "AI 코딩", "자동화", "리팩터링"]',
  734, 189, '2026-05-26 09:15:00+09'
),
(
  'n8n + Claude API로 이메일 자동 분류 및 답변 시스템',
  '하루 200통 들어오는 고객 이메일을 n8n 워크플로우로 분류 → Claude가 답변 초안 작성 → Slack 알림으로 사람이 승인. 응답 시간 4시간 → 30분으로 단축.',
  'https://news.ycombinator.com/item?id=39852514',
  'velog', 'automation_pro', 'ko', '중급', 0.84, 'experience',
  '["n8n", "Claude API", "AI 자동화", "워크플로우"]',
  298, 65, '2026-05-24 16:20:00+09'
),
(
  'Cursor Composer로 풀스택 앱 만들기 - 라이브 코딩 기록',
  'Cursor Composer로 Next.js + Supabase + Stripe 앱을 4시간 만에 만든 과정 기록. 작동하는 코드 80%, 디버깅 20%. 가장 큰 교훈: 작은 기능 단위로 쪼개기.',
  'https://www.reddit.com/r/cursor/',
  'reddit', 'fullstack_dev', 'en', '중급', 0.88, 'tutorial',
  '["Cursor", "Composer", "AI 코딩", "Next.js"]',
  456, 112, '2026-05-25 18:30:00+09'
),
(
  'Zapier + ChatGPT로 사내 슬랙 봇 만들기 (노코드)',
  '개발자 아닌데 슬랙 알림 봇 만들고 싶을 때. Zapier 트리거 + ChatGPT 액션 + 슬랙 메시지로 끝. 코드 한 줄 없이 30분.',
  'https://zapier.com/blog/how-to-build-chatgpt-slack-bot/',
  'tistory', 'no_code_kim', 'ko', '입문', 0.76, 'tutorial',
  '["Zapier", "ChatGPT", "노코드", "AI 자동화", "입문"]',
  134, 32, '2026-05-22 11:00:00+09'
),

-- ===== AI 엔지니어링 =====
(
  '프로덕션 LLM 앱 비용 60% 절감한 5가지 기법',
  '월 $15,000 쓰던 LLM 비용을 $6,000으로 줄인 실전 기법: 1) 프롬프트 캐싱 적극 활용 2) 라우팅 (쉬운 건 Haiku, 어려운 건 Sonnet) 3) 응답 압축 4) 배치 처리 5) 임베딩 재사용. 각 기법별 절감 비율 데이터.',
  'https://news.ycombinator.com/item?id=47160232',
  'hn', 'ai_app_founder', 'en', '고급', 0.95, 'experience',
  '["AI 엔지니어링", "비용 최적화", "프롬프트 캐싱", "프로덕션"]',
  892, 234, '2026-05-26 06:00:00+09'
),
(
  'FastAPI + Anthropic SDK 스트리밍 응답 구현 가이드',
  'SSE로 Claude 응답을 실시간 스트리밍하는 패턴. asyncio 활용, 백프레셔 처리, 클라이언트 재연결 로직까지. 코드 예시 250줄 첨부.',
  'https://fastapi.tiangolo.com/advanced/openapi-callbacks/',
  'velog', 'backend_eng', 'ko', '중급', 0.89, 'tutorial',
  '["FastAPI", "Anthropic", "스트리밍", "AI 엔지니어링"]',
  234, 52, '2026-05-23 15:30:00+09'
),
(
  'AI 앱 배포: Railway vs Vercel vs Fly.io 1년 운영 비교',
  '같은 AI 앱을 3개 플랫폼에 배포해서 1년 운영. Railway: 셋업 빠르고 DB 통합 편함, Vercel: 프론트엔드 압도적, Fly.io: 리전 가까워서 latency 최저. 가격은 비슷.',
  'https://channel.io/ko/blog/articles/what-is-harness-2611ddf1',
  'github_trending', 'devops_eng', 'en', '중급', 0.86, 'discussion',
  '["Railway", "Vercel", "Fly.io", "AI 엔지니어링", "배포"]',
  445, 78, '2026-05-25 10:45:00+09'
);


-- ============================================
-- CONTENT-NODE MAPPING (대주제 N:N 매핑)
-- 7개 대주제: 1=프롬프트 엔지니어링, 2=Agentic AI, 3=멀티모달 AI,
--           4=RAG & 지식 관리, 5=오픈소스 AI, 6=AI 워크플로우 & 자동화, 7=AI 엔지니어링
-- relevance_score 0.5 이상만 매핑 (운영 기준)
-- ============================================

INSERT INTO content_node_mapping (content_id, node_id, relevance_score) VALUES
-- content_id 1: Claude XML 태그 → 프롬프트 엔지니어링(주), AI 엔지니어링(부)
(1, 1, 0.95), (1, 7, 0.55),
-- content_id 2: CoT 비교 → 프롬프트 엔지니어링(주), AI 엔지니어링(부)
(2, 1, 0.92), (2, 7, 0.62),
-- content_id 3: 프롬프트 기초 → 프롬프트 엔지니어링(주)
(3, 1, 0.98),
-- content_id 4: MCP 5개 연동 → Agentic AI(주), AI 워크플로우(부)
(4, 2, 0.95), (4, 6, 0.70), (4, 7, 0.55),
-- content_id 5: 에이전트 프레임워크 비교 → Agentic AI(주)
(5, 2, 0.97),
-- content_id 6: MCP 입문 → Agentic AI(주)
(6, 2, 0.93),
-- content_id 7: Sora 2.0 → 멀티모달 AI(주)
(7, 3, 0.98),
-- content_id 8: Flux vs SDXL → 멀티모달 AI(주)
(8, 3, 0.96),
-- content_id 9: 멀티모달 RAG → 멀티모달 AI(주), RAG(주)
(9, 3, 0.88), (9, 4, 0.92),
-- content_id 10: 사내 위키 RAG → RAG(주), AI 엔지니어링(부)
(10, 4, 0.97), (10, 7, 0.65),
-- content_id 11: Obsidian + Claude → RAG(주), AI 워크플로우(부)
(11, 4, 0.90), (11, 6, 0.65),
-- content_id 12: pgvector 튜닝 → RAG(주), AI 엔지니어링(부)
(12, 4, 0.93), (12, 7, 0.70),
-- content_id 13: RAG 입문 → RAG(주), 프롬프트(부)
(13, 4, 0.95), (13, 1, 0.55),
-- content_id 14: Llama 4 한국어 → 오픈소스 AI(주)
(14, 5, 0.96),
-- content_id 15: Ollama + Mistral → 오픈소스 AI(주), AI 워크플로우(부)
(15, 5, 0.94), (15, 6, 0.60),
-- content_id 16: vLLM Qwen → 오픈소스 AI(주), AI 엔지니어링(부)
(16, 5, 0.92), (16, 7, 0.72),
-- content_id 17: HuggingFace Spaces → 오픈소스 AI(주), AI 엔지니어링(부)
(17, 5, 0.85), (17, 7, 0.62),
-- content_id 18: Claude Code 47PR → AI 워크플로우(주), Agentic AI(부)
(18, 6, 0.95), (18, 2, 0.65), (18, 7, 0.55),
-- content_id 19: n8n + Claude → AI 워크플로우(주)
(19, 6, 0.96),
-- content_id 20: Cursor Composer → AI 워크플로우(주), AI 엔지니어링(부)
(20, 6, 0.90), (20, 7, 0.65),
-- content_id 21: Zapier 노코드 → AI 워크플로우(주)
(21, 6, 0.92),
-- content_id 22: LLM 비용 절감 → AI 엔지니어링(주), 프롬프트(부)
(22, 7, 0.97), (22, 1, 0.55),
-- content_id 23: FastAPI 스트리밍 → AI 엔지니어링(주)
(23, 7, 0.94),
-- content_id 24: AI 앱 배포 비교 → AI 엔지니어링(주)
(24, 7, 0.93);


-- ============================================
-- 검증 쿼리 (실행 후 확인용)
-- ============================================
-- SELECT COUNT(*) AS total_content FROM content;                   -- 24
-- SELECT COUNT(*) AS total_mappings FROM content_node_mapping;     -- 약 40개
-- SELECT n.name, COUNT(cnm.content_id) AS content_count
-- FROM curriculum_nodes n
-- LEFT JOIN content_node_mapping cnm ON cnm.node_id = n.id
-- GROUP BY n.name ORDER BY n.id;
