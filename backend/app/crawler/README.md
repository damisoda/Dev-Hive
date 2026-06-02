# crawler — 데이터 수집

여러 소스에서 콘텐츠를 수집해 공통 `ContentSchema`로 정규화하고 `data/raw/`에 적재한다.
적재된 JSON은 태깅 파이프라인(`scripts/run_tagging_pipeline.py`)의 입력이 된다.

## 구성 (구현됨)
- `normalizer.py` — 공통 정규화 스키마 `ContentSchema` + `normalize()` 헬퍼 (전 소스 공통)
- `reddit_crawler.py` — Reddit PRAW (self-text 후기 중심, 크레덴셜 필요)
- `hackernews_crawler.py` — HN Algolia API
- `github_crawler.py` — GitHub Search API (AI 키워드 검색, stars 정렬) + README fetch로 본문 보강
- `huggingface_crawler.py` — HuggingFace daily papers API
- `run_crawler.py` — 멀티소스 수집 오케스트레이션 → `data/raw/<source>_YYYYMMDD.json`
- `eval/` — 소스별 수집 품질 점검 스크립트 (`hf_eval.py`, `hn_eval.py`)

`source` 값: `reddit` · `hn` · `github_trending` · `huggingface`

## 로드맵 (미구현)
- Velog / Tistory — 한국어 경험형 블로그 (RSS). 현재 미구현, 별도 작업으로 분리.
- X / Threads — Apify 스크레이퍼 일회성 수집.

## 필터링
- 1단계 (소스 자체): 정렬·engagement·URL 중복 제거 (각 크롤러 및 `run_crawler`)
- 2단계 (태깅 파이프라인): Haiku `quality_score` 임계값 미만 콘텐츠는 적재 제외

## 출력 포맷
```json
{
  "title": "", "body": "", "url": "",
  "source": "reddit", "author_name": "",
  "language": "en", "published_at": "ISO-8601",
  "engagement": {"likes": 0, "comments": 0}
}
```
