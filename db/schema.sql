-- Dev-Hive DB 스키마 v1
-- PostgreSQL + pgvector
-- 테이블 6종: users, content, curriculum_nodes, content_node_mapping, user_read_events, node_links

CREATE EXTENSION IF NOT EXISTS vector;

-- 1. 유저
CREATE TABLE IF NOT EXISTS users (
    id                 SERIAL PRIMARY KEY,
    username           VARCHAR(50) UNIQUE,            -- HIVE-100: 로그인 아이디(신규 가입 필수, 레거시 계정은 NULL)
    password_hash      VARCHAR(255),                  -- HIVE-100: bcrypt 해시(레거시는 NULL → 로그인 불가)
    display_name       VARCHAR(100) NOT NULL,
    persona            VARCHAR(20) NOT NULL DEFAULT '개발자',
    onboarding_answers JSONB,
    profile_vector     vector(1536),
    current_level      VARCHAR(10) DEFAULT '입문',
    influence_score    INT DEFAULT 0,
    created_at         TIMESTAMPTZ DEFAULT NOW()
);

-- 2. 콘텐츠 (source/author/tags를 필드로 내장)
CREATE TABLE IF NOT EXISTS content (
    id                  SERIAL PRIMARY KEY,
    title               VARCHAR(500) NOT NULL,
    body                TEXT NOT NULL,
    url                 VARCHAR(2000) UNIQUE,
    source              VARCHAR(20) NOT NULL,        -- reddit, hn, github_trending, huggingface, velog, tistory
    author_name         VARCHAR(200),
    uploaded_by         INT REFERENCES users(id),    -- 유저 업로드 시에만
    language            VARCHAR(5) DEFAULT 'en',     -- en / ko
    difficulty          VARCHAR(10),                 -- 입문 / 중급 / 고급
    quality_score       FLOAT,                       -- 0.0 ~ 1.0
    content_type        VARCHAR(20),                 -- experience / tutorial / concept / tool / discussion
    tags                JSONB DEFAULT '[]',          -- ["Cursor", "Claude Code", ...]
    synthesis           JSONB,                       -- HIVE-41 가공 카드(synthesized_card). NULL이면 원문 링크 폴백
    text_embedding      vector(1536),                -- OpenAI text-embedding-3-small (원문 고정, 가공본 임베딩 X)
    graph_embedding     vector(256),                 -- GraphSAGE 산출물 (Layer 2, NULL 가능)
    engagement_likes    INT DEFAULT 0,
    engagement_comments INT DEFAULT 0,
    published_at        TIMESTAMPTZ,
    crawled_at          TIMESTAMPTZ DEFAULT NOW(),
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- 3. 커리큘럼 노드 (대주제 7개 + Auto-HKG 하위 노드)
CREATE TABLE IF NOT EXISTS curriculum_nodes (
    id                SERIAL PRIMARY KEY,
    name              VARCHAR(100) NOT NULL,
    description       TEXT,
    parent_id         INT REFERENCES curriculum_nodes(id),
    is_auto_generated BOOLEAN DEFAULT FALSE,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

-- 4. 콘텐츠 ↔ 노드 N:N 매핑
CREATE TABLE IF NOT EXISTS content_node_mapping (
    content_id      INT REFERENCES content(id) ON DELETE CASCADE,
    node_id         INT REFERENCES curriculum_nodes(id) ON DELETE CASCADE,
    relevance_score FLOAT NOT NULL DEFAULT 0.0,
    PRIMARY KEY (content_id, node_id)
);

-- 5. 유저 읽음 이력
CREATE TABLE IF NOT EXISTS user_read_events (
    id         SERIAL PRIMARY KEY,
    user_id    INT REFERENCES users(id) ON DELETE CASCADE,
    content_id INT REFERENCES content(id) ON DELETE CASCADE,
    read_at    TIMESTAMPTZ DEFAULT NOW()
);

-- 6b. 유저 콘텐츠 피드백 (HIVE-37) — (user, content)당 1행, 최신값 upsert
CREATE TABLE IF NOT EXISTS user_content_feedback (
    user_id    INT REFERENCES users(id) ON DELETE CASCADE,
    content_id INT REFERENCES content(id) ON DELETE CASCADE,
    feedback   VARCHAR(20) NOT NULL,  -- understood / too_hard / want_more / not_interested
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (user_id, content_id)
);
CREATE INDEX IF NOT EXISTS idx_ucf_user ON user_content_feedback(user_id);

-- 6. 노드 간 소프트 링크 (Layer 2부터 활용)
CREATE TABLE IF NOT EXISTS node_links (
    source_node_id INT REFERENCES curriculum_nodes(id) ON DELETE CASCADE,
    target_node_id INT REFERENCES curriculum_nodes(id) ON DELETE CASCADE,
    weight         FLOAT DEFAULT 0.5,
    PRIMARY KEY (source_node_id, target_node_id)
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_content_source ON content(source);
CREATE INDEX IF NOT EXISTS idx_content_tags ON content USING GIN(tags);
CREATE INDEX IF NOT EXISTS idx_content_quality ON content(quality_score);
CREATE INDEX IF NOT EXISTS idx_content_embedding ON content USING ivfflat (text_embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS idx_cnm_node ON content_node_mapping(node_id);
CREATE INDEX IF NOT EXISTS idx_ure_user ON user_read_events(user_id);
