-- HIVE-100: 인증 컬럼 추가 (아이디/비밀번호 회원가입·로그인)
--
-- users에 username(로그인 아이디) + password_hash(bcrypt) 추가.
-- 신규 가입은 둘 다 채우고, 기존(레거시) 계정은 NULL로 둔다 → 로그인 불가하지만
-- read_events/feedback 등 기존 데이터는 user_id로 그대로 참조된다.
-- username은 NULL 다수 허용(레거시), 비-NULL은 UNIQUE(가입 시 중복 차단).
--
-- 멱등: ADD COLUMN IF NOT EXISTS + CREATE UNIQUE INDEX IF NOT EXISTS → 2회 실행 무해.
--
-- 실행:
--   psql $DATABASE_URL -f db/migrate_HIVE100_auth.sql

BEGIN;

ALTER TABLE users ADD COLUMN IF NOT EXISTS username      VARCHAR(50);
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255);

-- 비-NULL username만 유일성 보장(레거시 NULL 다수 허용).
CREATE UNIQUE INDEX IF NOT EXISTS ux_users_username ON users (username);

DO $$
DECLARE
  legacy INT;
BEGIN
  SELECT COUNT(*) INTO legacy FROM users WHERE username IS NULL;
  RAISE NOTICE 'HIVE-100 migration: 레거시(username NULL=로그인불가) 계정 = %', legacy;
END $$;

COMMIT;
