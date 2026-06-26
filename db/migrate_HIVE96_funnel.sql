-- HIVE-96: 추천 funnel 계측 — 노출(impression)/클릭(click) 로깅. 읽음은 user_read_events.
-- CTR = clicks/impressions, read-through = reads-of-impressed/impressions.
-- 멱등: CREATE TABLE/INDEX IF NOT EXISTS.
CREATE TABLE IF NOT EXISTS recommend_events (
    id         SERIAL PRIMARY KEY,
    user_id    INT REFERENCES users(id)   ON DELETE CASCADE,
    content_id INT REFERENCES content(id) ON DELETE CASCADE,
    event_type VARCHAR(20) NOT NULL,       -- 'impression' | 'click'
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_recev_user        ON recommend_events(user_id);
CREATE INDEX IF NOT EXISTS idx_recev_type_time   ON recommend_events(event_type, created_at);
CREATE INDEX IF NOT EXISTS idx_recev_content     ON recommend_events(content_id);
