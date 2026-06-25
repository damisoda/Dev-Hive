-- HIVE-28: X 크롤러 engagement 확장 — retweets / views 컬럼 추가
ALTER TABLE content ADD COLUMN IF NOT EXISTS engagement_retweets INT DEFAULT 0;
ALTER TABLE content ADD COLUMN IF NOT EXISTS engagement_views    INT DEFAULT 0;
