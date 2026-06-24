-- HIVE-62: 비한국어 콘텐츠 synthesis 캐시 무효화
--
-- synthesizer.py 프롬프트가 '원문 언어 출력' → '한국어 출력'으로 변경됨에 따라
-- language <> 'ko' 인 기존 synthesis(영어 출력) 캐시를 NULL로 초기화한다.
-- lazy_synthesis.ensure_synthesis()가 다음 요청 시 한국어로 재생성한다.
--
-- 멱등: 이미 NULL인 행에 NULL을 쓰는 것은 무해하다(2회 실행해도 동일 결과).
-- 현재 DB 구성상 language <> 'ko' = 'en' 한정 (zh 데이터 없음).
--
-- dry-run 확인:
--   SELECT language, COUNT(*) FROM content WHERE language <> 'ko' AND synthesis IS NOT NULL GROUP BY language;
--
-- 실행:
--   psql $DATABASE_URL -f db/migrate_HIVE62_synthesis_null.sql

BEGIN;

-- 영향 행수 확인용
DO $$
DECLARE
  affected INT;
BEGIN
  SELECT COUNT(*) INTO affected FROM content WHERE language <> 'ko' AND synthesis IS NOT NULL;
  RAISE NOTICE 'HIVE-62 migration: synthesis NULL 대상 행수 = %', affected;
END $$;

UPDATE content
SET synthesis = NULL
WHERE language <> 'ko';

COMMIT;
