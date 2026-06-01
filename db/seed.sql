-- 대주제 7개 시드 데이터
-- 같은 seed 파일을 여러 번 실행해도 동일한 대주제가 중복 생성되지 않도록 name 기준으로 확인한다.

INSERT INTO curriculum_nodes (name, description, is_auto_generated)
SELECT seed.name, seed.description, FALSE
FROM (
    VALUES
        ('프롬프트 엔지니어링', '프롬프트 설계, 시스템 프롬프트, CoT, few-shot, 출력 제어, 프롬프트 최적화'),
        ('Agentic AI', '자율 에이전트, MCP, 멀티 에이전트, 도구 호출, 오케스트레이션, 하네스 엔지니어링'),
        ('멀티모달 AI', '이미지/비디오/오디오 생성 및 이해, 비전, 크로스모달 응용'),
        ('RAG & 지식 관리', '벡터 DB, 임베딩, 검색 증강 생성, 지식 베이스, 시맨틱 서치, 문서 QA'),
        ('오픈소스 AI', '오픈 모델, Ollama, HuggingFace, vLLM, fine-tuning, 로컬 추론'),
        ('AI 워크플로우 & 자동화', 'n8n, Make, Zapier, Copilot, Cursor, 업무 자동화, 코딩 보조, 파이프라인 설계'),
        ('AI 엔지니어링', 'AI API 활용 개발, 풀스택 빌딩, 배포, MLOps, 프로덕션, 사이드 프로젝트')
) AS seed(name, description)
WHERE NOT EXISTS (
    SELECT 1
    FROM curriculum_nodes existing
    WHERE existing.name = seed.name
);
