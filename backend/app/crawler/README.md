# crawler — 데이터 수집

6개 소스에서 콘텐츠를 수집하고 공통 Content 스키마로 정규화한다.

## 구성 (예정)
- `normalizer.py` — 공통 정규화 스키마 (전 소스 공통, 먼저 구현)
- `reddit_crawler.py` — Reddit PRAW
- `hackernews_crawler.py` — HN Algolia API
- `github_crawler.py` — GitHub Trending HTML 파싱
- `velog_crawler.py` — Velog GraphQL
- `tistory_crawler.py` — Tistory RSS
- `huggingface_crawler.py` — HF daily papers API

## 필터링
품질 필터링 기준은 `docs/크롤링_품질필터링_가이드.md` 참조.
- 1단계: 소스 자체 필터 (top 정렬 + engagement)
- 2단계: 규칙 기반 필터 (flair, 길이, 언어, 중복)

## 출력 포맷
```json
{
  "title": "", "body": "", "url": "",
  "source": "reddit", "author_name": "",
  "language": "en", "published_at": "ISO-8601",
  "engagement": {"likes": 0, "comments": 0}
}
```
