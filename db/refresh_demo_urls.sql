-- 데모용 시드 URL을 실제 작동하는 URL로 교체 + 임베딩 초기화
-- 적용: docker exec -i devhive-db psql -U devhive -d devhive < db/refresh_demo_urls.sql
-- 적용 후: cd backend && python scripts/embed_seed.py 로 임베딩 재생성

-- ============================================
-- URL 업데이트 (24건) — 실제 존재하는 URL로
-- ============================================

-- 프롬프트 엔지니어링
UPDATE content SET url = 'https://velog.io/@skysoo/Claude-Code-%EC%99%84%EB%B2%BD-%EA%B0%80%EC%9D%B4%EB%93%9C-%ED%95%9C%EA%B8%80-%EC%9A%94%EC%95%BD%EB%B3%B8' WHERE id = 1;
UPDATE content SET url = 'https://news.ycombinator.com/item?id=42560558' WHERE id = 2;
UPDATE content SET url = 'https://velog.io/@rollingman1/Claude-AI-%EB%AC%B4%EB%A3%8C%EB%A1%9C-pdf%EB%A1%9C-%EB%8C%80%ED%99%94%ED%95%98%EA%B8%B0.-ChatGPT-Pro-%ED%95%84%EC%9A%94%EC%97%86%EC%96%B4%EC%9A%94' WHERE id = 3;

-- Agentic AI
UPDATE content SET url = 'https://velog.io/@windowook/Claude-Code-ContextEngineering' WHERE id = 4;
UPDATE content SET url = 'https://news.ycombinator.com/item?id=47000034' WHERE id = 5;
UPDATE content SET url = 'https://velog.io/@strurao/Claude-Code%EC%9D%98-%EA%B5%AC%EC%A1%B0-%EC%84%A4%EA%B3%84-%ED%95%98%EB%84%A4%EC%8A%A4%EB%8A%94-%EC%96%87%EA%B2%8C-%EC%A7%80%EB%8A%A5%EC%9D%80-%EB%AA%A8%EB%8D%B8%EC%97%90' WHERE id = 6;

-- 멀티모달 AI
UPDATE content SET url = 'https://huggingface.co/blog/saumitras/colpali-milvus-multimodal-rag' WHERE id = 7;
UPDATE content SET url = 'https://huggingface.co/blog/Omartificial-Intelligence-Space/building-multimodal-rag-systems' WHERE id = 8;
UPDATE content SET url = 'https://huggingface.co/learn/cookbook/en/multimodal_rag_using_document_retrieval_and_vlms' WHERE id = 9;

-- RAG & 지식 관리
UPDATE content SET url = 'https://news.ycombinator.com/item?id=45645349' WHERE id = 10;
UPDATE content SET url = 'https://velog.io/@softer/Claude-Code-%EC%82%AC%EC%9A%A9-%ED%9A%8C%EA%B3%A0' WHERE id = 11;
UPDATE content SET url = 'https://github.com/pgvector/pgvector' WHERE id = 12;
UPDATE content SET url = 'https://news.ycombinator.com/item?id=37505687' WHERE id = 13;

-- 오픈소스 AI
UPDATE content SET url = 'https://www.reddit.com/r/LocalLLaMA/' WHERE id = 14;
UPDATE content SET url = 'https://github.com/ollama/ollama' WHERE id = 15;
UPDATE content SET url = 'https://github.com/vllm-project/vllm' WHERE id = 16;
UPDATE content SET url = 'https://huggingface.co/docs/hub/en/spaces-overview' WHERE id = 17;

-- AI 워크플로우 & 자동화
UPDATE content SET url = 'https://velog.io/@softer/Claude-Code-%EC%82%AC%EC%9A%A9-%ED%9A%8C%EA%B3%A0' WHERE id = 18;
UPDATE content SET url = 'https://news.ycombinator.com/item?id=39852514' WHERE id = 19;
UPDATE content SET url = 'https://www.reddit.com/r/cursor/' WHERE id = 20;
UPDATE content SET url = 'https://zapier.com/blog/how-to-build-chatgpt-slack-bot/' WHERE id = 21;

-- AI 엔지니어링
UPDATE content SET url = 'https://news.ycombinator.com/item?id=47160232' WHERE id = 22;
UPDATE content SET url = 'https://fastapi.tiangolo.com/advanced/openapi-callbacks/' WHERE id = 23;
UPDATE content SET url = 'https://news.ycombinator.com/item?id=45645349' WHERE id = 24;


-- ============================================
-- 임베딩 초기화 (text_embedding NULL로)
-- 이후 backend/scripts/embed_seed.py 재실행으로 재생성한다.
-- graph_embedding은 어차피 NULL이라 손댈 필요 없음.
-- ============================================

UPDATE content SET text_embedding = NULL;


-- ============================================
-- 검증 쿼리 (수동 확인용)
-- ============================================
-- SELECT id, title, url FROM content ORDER BY id;
-- SELECT COUNT(*) FROM content WHERE text_embedding IS NULL;  -- 24
-- SELECT COUNT(*) FROM content WHERE url LIKE 'https://%example%';  -- 0
