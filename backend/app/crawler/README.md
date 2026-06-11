# crawler — 데이터 수집 + QC 게이트

여러 소스에서 콘텐츠를 수집해 공통 `ContentSchema`로 정규화하고 `data/raw/`에 적재한다.
적재된 JSON은 태깅 파이프라인(`scripts/run_tagging_pipeline.py` → `app/tagging/ingest.py`)의 입력이 된다.

## 구성 (구현됨)
- `normalizer.py` — 공통 정규화 스키마 `ContentSchema` + `normalize()` 헬퍼 (전 소스 공통)
- `qc_gate.py` — **적재 전 QC 게이트(HIVE-40)**. 태깅(Haiku) 전에 무료 휴리스틱으로 junk를 거른다
- `velog_crawler.py` — Velog GraphQL 검색 (경험글 중심, 7개 대주제 키워드)
- `velog_beginner_crawler.py` — Velog 입문자 후기 전용 (키워드 완화판)
- `reddit_crawler.py` — Reddit PRAW (self-text 후기 중심, 크레덴셜 필요)
- `reddit_public_crawler.py` — Arctic Shift 공개 아카이브 API (인증 불필요 대안)
- `github_crawler.py` — GitHub Search API (AI 키워드 검색, stars 정렬) + README fetch로 본문 보강
- `github_discussions_crawler.py` — GitHub Discussions GraphQL (실사용 경험담)
- `huggingface_crawler.py` — HuggingFace daily papers API
- `x_crawler.py` — Apify X 스크레이퍼, 시드유저 14인 전문가 계정 `from:<handle>` 크롤 (HIVE-28, 일회성)
- `run_crawler.py` — 멀티소스 수집 오케스트레이션 → `data/raw/<source>_YYYYMMDD.json`
- `scheduler.py` — apscheduler 기반 주기 크롤 (lazy import, `ENABLE_SCHEDULER=1`일 때만 가동)
- `google_drive_uploader.py` — 수집 덤프 Google Drive 백업
- `eval/` — 소스별 수집 품질 점검 스크립트 (`velog_eval.py`, `reddit_eval.py`, `github_discussions_eval.py`, `hf_eval.py` 등)

`source` 값: `velog` · `tistory` · `reddit` · `github_trending` · `huggingface` · `x`
(HackerNews는 데이터 품질 미달로 폐기 — QC 게이트가 `hn`을 자동 거부한다.)

## QC 게이트 (qc_gate.py, HIVE-40)

위치: 정규화 후 · 태깅 전. **precision 우선** — 애매하면 통과시키고 "확실한 junk"만 거른다.

- 소스 허용목록 (`hn` 등 미허용 소스 자동 거부) + `expected_source` 미스라벨 거부 (유저 업로드는 `expected_source="user"`로 우회)
- github_trending: stars(`engagement.likes`) < 100 거부 (`low_stars`)
- reddit: 서브레딧 큐레이션(저신뢰 서브레딧 거부) + 답 없는 Q&A 거부
- NSFW, 빈 본문, 배치 내 중복 거부
- x 전용: 본문 < 100자(`too_short`) · 라틴계 비영어(es/pt/fr/de/it 기능어 감지, `language_not_supported`) · 짧고 반응 전무(`zero_engagement_short`)

## 필터링 단계 (전체)
1. 소스 자체: 정렬·engagement·URL 중복 제거 (각 크롤러 및 `run_crawler`)
2. QC 게이트 (`qc_gate.py`): 위 휴리스틱 — LLM 비용 발생 전
3. 태깅 파이프라인: Haiku `quality_score` < 0.5 콘텐츠 적재 제외

## 출력 포맷
```json
{
  "title": "", "body": "", "url": "",
  "source": "velog", "author_name": "",
  "language": "ko", "published_at": "ISO-8601",
  "engagement": {"likes": 0, "comments": 0}
}
```
