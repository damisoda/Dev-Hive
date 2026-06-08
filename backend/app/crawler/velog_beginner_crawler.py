"""
Velog 입문자 경험담 크롤러 — 키워드 검색 전용.

기존 velog_crawler.py와 차이:
- 입문·초보·후기 중심 키워드만 사용
- _is_experience() 필터 미적용 (입문 후기는 경험 신호어 없이도 수집)
- MIN_LIKES=0, MIN_BODY=300 완화 (입문글은 좋아요·길이 적은 경향)
- 시드 유저 경로 없음 — 키워드 검색만
- 기존 velog_*.json의 seen URL 공유 → 기존 수집본과 중복 없음

실행:
    python -m app.crawler.velog_beginner_crawler
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from app.crawler.normalizer import ContentSchema, clean_body, normalize
from app.crawler.velog_crawler import (
    VELOG_GQL_URL,
    VELOG_PAGE_SIZE,
    VELOG_REQUEST_SLEEP,
    HTTP_TIMEOUT,
    _SEARCH_POSTS_QUERY,
    _POST_BODY_QUERY,
    _is_ai_related,
    _parse_dt,
    _make_url,
    _load_seen_urls,
    _gql,
)

logger = logging.getLogger(__name__)

BEGINNER_TARGET    = int(os.getenv("VELOG_BEGINNER_TARGET", "150"))
BEGINNER_MIN_BODY  = int(os.getenv("VELOG_BEGINNER_MIN_BODY", "300"))
BEGINNER_MAX_PAGES = int(os.getenv("VELOG_BEGINNER_MAX_PAGES", "20"))

# 입문·초보·후기 중심 키워드
BEGINNER_KEYWORDS: list[str] = [
    kw.strip()
    for kw in os.getenv(
        "VELOG_BEGINNER_KEYWORDS",
        # 직접적 입문/시작 표현
        "AI 입문,AI 처음,AI 시작,AI 독학,"
        "처음 써봤,처음 해봤,처음 사용,"
        "입문기,입문 후기,입문자,"
        # 사용 후기/체험기
        "AI 사용기,AI 후기,AI 체험기,AI 사용 후기,"
        "써봤습니다,써봤어요,해봤습니다,해봤어요,"
        "써보니,써보고,사용해보니,사용해보고,"
        "솔직 후기,솔직후기,사용 소감,"
        # 학습/공부 경험
        "AI 공부 후기,AI 공부일기,AI 학습 후기,"
        "독학 후기,독학기,공부 후기,"
        # 도입/적용 첫 경험
        "AI 도전,AI 첫 경험,첫인상,"
        "처음 접했,처음 도입,도입 후기,"
        # 초보 시각
        "초보자,AI 초보,비개발자,비전공자 AI,"
        "개발 못해도,코딩 모르는,"
        # 활용 일지
        "AI 활용 일지,AI 일지,사용 일지,"
        "ChatGPT 후기,클로드 후기,Cursor 후기",
    ).split(",")
    if kw.strip()
]

# 입문글 노이즈 제거용 — 튜토리얼·개념정리·뉴스는 제외
_EXCLUDE_SIGNALS: tuple[str, ...] = (
    "이란 무엇인가", "이란?", "개념 정리", "개념정리",
    "총정리", "완전 정복", "모든 것을", "정리해봤",
    "발표했", "출시됐", "업데이트됐", "릴리즈",
    "논문 리뷰", "논문 정리", "paper review",
)


def _is_not_tutorial(title: str, description: str) -> bool:
    text = (title + " " + description).lower()
    return not any(sig in text for sig in _EXCLUDE_SIGNALS)


def _fetch_body(username: str, url_slug: str) -> str:
    data = _gql(_POST_BODY_QUERY, {"username": username, "url_slug": url_slug})
    if not data:
        return ""
    raw = ((data.get("data") or {}).get("post") or {}).get("body") or ""
    return clean_body(raw)


def fetch_beginner_keyword(keyword: str, seen_urls: set[str]) -> list[ContentSchema]:
    results: list[ContentSchema] = []

    for page in range(BEGINNER_MAX_PAGES):
        offset = page * VELOG_PAGE_SIZE
        data = _gql(
            _SEARCH_POSTS_QUERY,
            {"keyword": keyword, "limit": VELOG_PAGE_SIZE, "offset": offset},
        )
        if not data:
            break

        posts: list[dict] = (
            (data.get("data") or {}).get("searchPosts") or {}
        ).get("posts") or []

        if not posts:
            break

        for post in posts:
            username: str = (post.get("user") or {}).get("username") or ""
            if not username or not post.get("url_slug"):
                continue

            url = _make_url(username, post["url_slug"])
            if url in seen_urls:
                continue

            if not _is_ai_related(post.get("tags") or []):
                continue

            # 입문 크롤러: _is_experience() 필터 미적용
            # 대신 튜토리얼·개념정리는 제외
            if not _is_not_tutorial(
                post.get("title") or "", post.get("short_description") or ""
            ):
                continue

            seen_urls.add(url)

            url_slug = post["url_slug"]
            body = _fetch_body(username, url_slug)
            time.sleep(VELOG_REQUEST_SLEEP)

            if len(body) < BEGINNER_MIN_BODY:
                continue

            item = normalize(
                title=post.get("title") or "",
                source="velog",
                url=url,
                published_at=_parse_dt(post.get("released_at")),
                body=body,
                author_name=username,
                language="ko",
                likes=int(post.get("likes") or 0),
                comments=int(post.get("comments_count") or 0),
            )
            if item:
                results.append(item)

        time.sleep(VELOG_REQUEST_SLEEP)

    logger.info("입문 키워드 '%s': %d건 수집", keyword, len(results))
    return results


def collect_velog_beginner(target: int = BEGINNER_TARGET) -> list[ContentSchema]:
    # 기존 velog_*.json seen URL 포함 → 기존 수집본과 중복 없음
    seen_urls = _load_seen_urls()
    logger.info("기존 seen URL %d건 로드", len(seen_urls))

    results: list[ContentSchema] = []

    for keyword in BEGINNER_KEYWORDS:
        if len(results) >= target:
            break
        results.extend(fetch_beginner_keyword(keyword, seen_urls))

    logger.info("Velog 입문 수집 완료: %d건", len(results))
    return results[:target]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    items = collect_velog_beginner()

    if not items:
        print("수집된 항목 없음")
    else:
        out = Path("data/raw")
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"velog_beginner_{datetime.utcnow().strftime('%Y%m%d')}.json"
        path.write_text(
            json.dumps([i.to_dict() for i in items], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n저장: {path} ({len(items)}건)")
