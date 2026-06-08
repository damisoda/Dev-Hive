"""
GitHub Discussions 경험담 크롤러 — GitHub GraphQL API 사용.
AI 관련 리포지토리 Discussions에서 실사용 경험담을 수집한다.

[임시 로직 — HIVE-31]
- 필터 기준(경험 신호어·제외 카테고리·제품 홍보 패턴)은 품질 평가를 거치며 반복 조정 중.
- TARGET_REPOS 선정 및 작성자 중복 제한(author ≤ 2건)도 실험적 수치.
- 장기적으로는 langdetect 기반 언어 태깅 및 벡터 유사도 dedup 으로 대체 예정.

필요: GITHUB_TOKEN 환경변수
  github.com/settings/tokens → Generate new token (classic) → public_repo 체크
  또는 Fine-grained token → read:discussion

실행:
    python -m app.crawler.github_discussions_crawler
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from app.crawler.normalizer import ContentSchema, clean_body, normalize

logger = logging.getLogger(__name__)

GITHUB_TOKEN                    = os.getenv("GITHUB_TOKEN", "")
GITHUB_DISCUSSIONS_LOOKBACK_DAYS = int(os.getenv("GITHUB_DISCUSSIONS_LOOKBACK_DAYS", "180"))
GITHUB_DISCUSSIONS_MIN_BODY     = int(os.getenv("GITHUB_DISCUSSIONS_MIN_BODY", "300"))
GITHUB_DISCUSSIONS_TARGET       = int(os.getenv("GITHUB_DISCUSSIONS_TARGET", "300"))
GITHUB_DISCUSSIONS_PAGE_SIZE    = int(os.getenv("GITHUB_DISCUSSIONS_PAGE_SIZE", "50"))
GITHUB_DISCUSSIONS_SLEEP        = float(os.getenv("GITHUB_DISCUSSIONS_SLEEP", "1.0"))

_GQL_URL = "https://api.github.com/graphql"

# 경험담이 많은 AI 관련 리포지토리 (owner, repo)
TARGET_REPOS: list[tuple[str, str]] = [
    ("langchain-ai",        "langchain"),
    ("ollama",              "ollama"),
    ("open-webui",          "open-webui"),
    ("n8n-io",              "n8n"),
    ("microsoft",           "autogen"),
    ("crewAI-inc",          "crewAI"),
    ("comfyanonymous",      "ComfyUI"),
    ("oobabooga",           "text-generation-webui"),
    ("lobehub",             "lobe-chat"),
    ("ag2ai",               "ag2"),
    ("run-llama",           "llama_index"),
    # 추가: 실사용 경험담 많은 리포
    ("langgenius",          "dify"),           # 노코드 AI 워크플로우
    ("invoke-ai",           "InvokeAI"),       # 이미지 생성 경험
    ("imartinez",           "privateGPT"),     # 로컬 AI 경험
    ("BerriAI",             "litellm"),        # LLM 라우팅 경험
    ("mudler",              "LocalAI"),        # 로컬 모델 경험
]

# 경험담 카테고리 slug — 해당 카테고리면 experience 신호어 없이도 통과
_EXPERIENCE_CATEGORY_SLUGS: frozenset[str] = frozenset({
    "show-and-tell", "showcase", "examples",
    "use-cases", "share", "built-with",
})

# 제외 카테고리 — 버그·기능요청·Q&A 등
_SKIP_CATEGORY_SLUGS: frozenset[str] = frozenset({
    "q-a", "q&a", "help", "help-wanted",
    "bug", "bugs", "bug-report", "bug-reports",
    "feature-request", "feature-requests",
    "announcements", "release", "releases",
    "polls", "rfcs", "ideas",
})

# 버그·질문 제목 신호어 — 경험담이 아닌 트러블슈팅·도움 요청
_BUG_OR_HELP_TITLE_SIGNALS: tuple[str, ...] = (
    "help needed", "help wanted", "help:",
    "not working", "doesn't work", "not work", "no longer works",
    "stopped working", "not working anymore", "broken",
    "can't ", "cannot ", "won't ", "doesn't ", "doesn't show",
    "not visible", "not showing", "not loading", "not saving",
    "failed to ", "fails to ", "fail to ",
    "error:", "error when", "error in", "error with",
    "[bug]", "[issue]", "[error]", "[question]", "[q]",
    "why is", "why does", "why can't", "why won't",
    "how to ", "how do i ", "how can i ",
    "is it possible", "is there a way",
    "any update on", "any news on", "eta for", "any eta",
    "questions for", "questions about", "questions on",
    "404", "500 error", "crash", "crashes",
    "remains public", "still not", "still broken",
)

# 제품 홍보 body 신호어 — 링크 덤프·서비스 공지
_PRODUCT_PROMO_BODY_SIGNALS: tuple[str, ...] = (
    "website:", "mcp server:", "mcp endpoint:",
    "parent brand:", "product hunt", "ph launch",
    "pricing:", "free tier:", "enterprise plan",
    "sign up at", "sign up here", "try it at https",
    "check it out at https", "available at https",
    # Dify/GitHub 이슈 템플릿 남용 감지
    "i have searched for existing issues",
    "i confirm that i am using english to submit",
    "for chinese users",
)

# 기능 제안·PR 제출 전 피드백 요청 네거티브 필터
_FEATURE_REQUEST_TITLE_SIGNALS: tuple[str, ...] = (
    "feature proposal", "feature request", "feature suggestion",
    "[feature]", "[request]", "[proposal]", "[rfc]",
    "proposal:", "request:", "suggestion:",
    "add support for", "please add", "would it be possible",
)

_FEATURE_REQUEST_BODY_SIGNALS: tuple[str, ...] = (
    "would like to propose", "i'd like to propose", "i would like to propose",
    "before submitting a pr", "submitting a pr", "open a pr", "opening a pr",
    "looking for feedback", "looking for thoughts", "looking for opinions",
    "would love to get feedback", "love to hear your thoughts",
    "i would like to suggest", "i'd like to suggest",
    "feature request", "feature proposal",
    "i'd like to request", "would it be possible to add",
    "could we add", "could we have", "would be great to have",
    "i think it would be", "it would be great if",
)

# 경험 신호어 — title + body 앞 500자 검사
_EXPERIENCE_SIGNALS: tuple[str, ...] = (
    "i tried", "i've been", "i built", "i made", "i created",
    "i started", "i recently", "i finally", "i found",
    "i've been using", "i've used", "i run ", "i'm running",
    "i switched", "i replaced", "i automated", "i set up",
    "i've been experimenting", "i've been playing",
    "we built", "we use", "we've been", "we're using",
    "got it working", "got it running", "managed to", "finally got",
    "running locally", "my setup", "my config", "my workflow",
    "my experience", "my process", "my approach",
    "lessons learned", "what i learned", "what i found",
    "sharing my", "here's how i", "here's what i",
    "this is how i", "this is my",
    "as a beginner", "just started", "new to ", "getting started",
    "in my experience", "from my experience",
    "sharing", "built this", "made this",
)

_DISCUSSIONS_GQL = """
query GetDiscussions($owner: String!, $repo: String!, $first: Int!, $after: String) {
  repository(owner: $owner, name: $repo) {
    discussions(first: $first, after: $after, orderBy: {field: CREATED_AT, direction: DESC}) {
      nodes {
        title
        body
        createdAt
        url
        author { login }
        upvoteCount
        comments { totalCount }
        category { name slug }
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
}
"""


def _gql(variables: dict) -> dict | None:
    if not GITHUB_TOKEN:
        logger.error("GITHUB_TOKEN 환경변수가 없습니다. .env에 설정하세요.")
        return None
    try:
        resp = requests.post(
            _GQL_URL,
            json={"query": _DISCUSSIONS_GQL, "variables": variables},
            headers={
                "Authorization": f"Bearer {GITHUB_TOKEN}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        if resp.status_code == 429:
            retry = int(resp.headers.get("Retry-After", "60"))
            logger.warning("GitHub rate limit. %d초 대기", retry)
            time.sleep(retry)
            return None
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        logger.warning("GitHub GraphQL 실패: %s", exc)
        return None


def _is_experience(title: str, body: str) -> bool:
    text = (title + " " + body[:500]).lower()
    return any(sig in text for sig in _EXPERIENCE_SIGNALS)


def _is_feature_request(title: str, body: str) -> bool:
    title_lower = title.lower()
    body_front = body[:400].lower()
    return (
        any(sig in title_lower for sig in _FEATURE_REQUEST_TITLE_SIGNALS)
        or any(sig in body_front for sig in _FEATURE_REQUEST_BODY_SIGNALS)
    )


def _is_bug_or_help(title: str) -> bool:
    title_lower = title.lower()
    return any(sig in title_lower for sig in _BUG_OR_HELP_TITLE_SIGNALS)


def _is_product_promo(body: str) -> bool:
    body_front = body[:600].lower()
    return any(sig in body_front for sig in _PRODUCT_PROMO_BODY_SIGNALS)



def _parse(discussion: dict) -> ContentSchema | None:
    title = (discussion.get("title") or "").strip()
    raw_body = discussion.get("body") or ""
    body = clean_body(raw_body)

    if len(body) < GITHUB_DISCUSSIONS_MIN_BODY:
        return None

    category = discussion.get("category") or {}
    slug = (category.get("slug") or "").lower()

    if slug in _SKIP_CATEGORY_SLUGS:
        return None

    # 버그·도움요청 제목은 카테고리 무관 제외
    if _is_bug_or_help(title):
        return None

    # 기능 제안·PR 피드백 요청은 카테고리 무관 제외
    if _is_feature_request(title, body):
        return None

    # 제품 홍보 링크 덤프 제외
    if _is_product_promo(body):
        return None

    # show-and-tell 등 경험 카테고리는 신호어 없이 통과, 그 외는 신호어 필수
    if slug not in _EXPERIENCE_CATEGORY_SLUGS:
        if not _is_experience(title, body):
            return None

    created_str = discussion.get("createdAt") or ""
    try:
        published_at = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
    except ValueError:
        published_at = datetime.now(timezone.utc)

    return normalize(
        source="github_discussions",
        title=title,
        url=discussion.get("url") or "",
        body=body,
        likes=int(discussion.get("upvoteCount") or 0),
        comments=int((discussion.get("comments") or {}).get("totalCount") or 0),
        published_at=published_at,
        author_name=(discussion.get("author") or {}).get("login") or "",
        language="en",
    )


def _body_hash(body: str) -> str:
    return hashlib.md5(body[:800].encode("utf-8")).hexdigest()


def _collect_repo(
    owner: str,
    repo: str,
    cutoff: datetime,
    seen: set[str],
    seen_hashes: set[str] | None = None,
) -> list[ContentSchema]:
    results: list[ContentSchema] = []
    cursor: str | None = None

    while True:
        data = _gql({
            "owner": owner,
            "repo": repo,
            "first": GITHUB_DISCUSSIONS_PAGE_SIZE,
            "after": cursor,
        })
        if not data:
            break

        discussions_data = (
            (data.get("data") or {})
            .get("repository") or {}
        ).get("discussions") or {}

        nodes = discussions_data.get("nodes") or []
        page_info = discussions_data.get("pageInfo") or {}

        if not nodes:
            break

        cutoff_reached = False
        for disc in nodes:
            created_str = disc.get("createdAt") or ""
            try:
                created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            except ValueError:
                continue

            if created < cutoff:
                cutoff_reached = True
                break

            url = disc.get("url") or ""
            if not url or url in seen:
                continue

            item = _parse(disc)
            if item:
                h = _body_hash(item.body)
                if seen_hashes is not None and h in seen_hashes:
                    continue
                seen.add(url)
                if seen_hashes is not None:
                    seen_hashes.add(h)
                results.append(item)

        if cutoff_reached or not page_info.get("hasNextPage"):
            break

        cursor = page_info.get("endCursor")
        time.sleep(GITHUB_DISCUSSIONS_SLEEP)

    logger.info("%s/%s: %d건 수집", owner, repo, len(results))
    return results


def collect_github_discussions(target: int = GITHUB_DISCUSSIONS_TARGET) -> list[ContentSchema]:
    if not GITHUB_TOKEN:
        logger.error("GITHUB_TOKEN 없음. github.com/settings/tokens 에서 발급 후 .env에 추가하세요.")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=GITHUB_DISCUSSIONS_LOOKBACK_DAYS)
    results: list[ContentSchema] = []
    seen: set[str] = set()
    seen_hashes: set[str] = set()

    for owner, repo in TARGET_REPOS:
        if len(results) >= target:
            break
        results.extend(_collect_repo(owner, repo, cutoff, seen, seen_hashes))

    # 작성자별 최대 2건 — 좋아요 순 유지 (스팸 반복 게시 방지)
    from collections import defaultdict
    author_counts: dict[str, int] = defaultdict(int)
    deduped: list[ContentSchema] = []
    for item in sorted(results, key=lambda x: x.engagement.get("likes", 0), reverse=True):
        if author_counts[item.author_name] < 2:
            deduped.append(item)
            author_counts[item.author_name] += 1
    results = deduped

    logger.info("GitHub Discussions 최종 수집: %d건", len(results))
    return results[:target]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    items = collect_github_discussions()

    if not items:
        print("수집된 항목 없음. GITHUB_TOKEN 확인 후 재실행하세요.")
    else:
        out = Path("data/raw")
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"github_discussions_{datetime.utcnow().strftime('%Y%m%d')}.json"
        path.write_text(
            json.dumps([i.to_dict() for i in items], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n저장: {path} ({len(items)}건)")
