from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.crawler.normalizer import ContentSchema, normalize

logger = logging.getLogger(__name__)

GITHUB_API_URL = "https://api.github.com/search/repositories"

GITHUB_TARGET_ITEMS = int(os.getenv("GITHUB_TARGET_ITEMS", "300"))
GITHUB_MIN_STARS = int(os.getenv("GITHUB_MIN_STARS", "30"))
GITHUB_LOOKBACK_DAYS = int(os.getenv("GITHUB_LOOKBACK_DAYS", "30"))
GITHUB_PER_PAGE = min(int(os.getenv("GITHUB_PER_PAGE", "100")), 100)
GITHUB_MIN_PAGES_PER_QUERY = int(os.getenv("GITHUB_MIN_PAGES_PER_QUERY", "3"))
GITHUB_MAX_PAGES_PER_QUERY = int(os.getenv("GITHUB_MAX_PAGES_PER_QUERY", "5"))
GITHUB_REQUEST_SLEEP_SECONDS = float(os.getenv("GITHUB_REQUEST_SLEEP_SECONDS", "2.1"))
GITHUB_RATE_LIMIT_MAX_SLEEP_SECONDS = int(os.getenv("GITHUB_RATE_LIMIT_MAX_SLEEP_SECONDS", "60"))
GITHUB_MAX_SEARCHES_WITH_TOKEN = int(os.getenv("GITHUB_MAX_SEARCHES_WITH_TOKEN", "120"))
GITHUB_MAX_SEARCHES_WITHOUT_TOKEN = int(os.getenv("GITHUB_MAX_SEARCHES_WITHOUT_TOKEN", "10"))
HTTP_TIMEOUT_SECONDS = int(os.getenv("HTTP_TIMEOUT_SECONDS", "30"))
# README 본문 보강(레퍼런스 깊이). repo 설명 한 줄로는 학습 콘텐츠가 부실해 README를 body로 합친다.
# README 조회는 repo당 API 1콜이라 rate limit 보호를 위해 토큰이 있을 때만 호출한다.
GITHUB_FETCH_README = os.getenv("GITHUB_FETCH_README", "true").lower() in {"1", "true", "yes"}
GITHUB_README_MAX_CHARS = int(os.getenv("GITHUB_README_MAX_CHARS", "5000"))

GITHUB_SEARCH_TERMS = [
    term.strip()
    for term in os.getenv(
        "GITHUB_SEARCH_TERMS",
        "llm,large language model,generative ai,agent,agents,ai agent,"
        "multi agent,rag,retrieval augmented generation,vector database,"
        "embedding,semantic search,langchain,llamaindex,langgraph,crewai,"
        "autogen,mcp,model context protocol,ollama,vllm,lora,quantization,"
        "prompt engineering,workflow automation,llmops,mlops,multimodal",
    ).split(",")
    if term.strip()
]

CATEGORY_KEYWORDS = {
    "Prompt Engineering": (
        "prompt",
        "few-shot",
        "zero-shot",
        "chain of thought",
        "cot",
        "in-context learning",
    ),
    "Agentic AI": (
        "agent",
        "langgraph",
        "crewai",
        "autogen",
        "mcp",
        "model context protocol",
        "multi-agent",
    ),
    "Multimodal": (
        "multimodal",
        "sora",
        "runway",
        "kling",
        "text-to-video",
        "vision model",
    ),
    "RAG & Search": (
        "rag",
        "vector db",
        "pgvector",
        "pinecone",
        "semantic search",
        "chunking",
        "embedding",
    ),
    "OpenSource LLM": (
        "ollama",
        "vllm",
        "lora",
        "quantization",
        "llama3",
        "hf",
        "huggingface",
    ),
    "Automation": (
        "n8n",
        "make.com",
        "zapier",
        "workflow automation",
        "ai automation",
    ),
    "LLM Architecture": (
        "llm api",
        "mlops",
        "llmops",
        "langchain",
        "llamaindex",
        "production llm",
    ),
    "AI Tech Conference": (
        "Google I/O",
        "NVIDIA GTC",
        "Microsoft Build",
        "MS Build",
        "NeurIPS",
        "Apple WWDC",
    ),
}


def _keyword_to_regex(keyword: str) -> re.Pattern[str]:
    tokens = re.findall(r"[a-z0-9]+", keyword.casefold())
    if not tokens:
        return re.compile(r"a\Ab")

    pieces = []
    for index, token in enumerate(tokens):
        escaped = re.escape(token)
        if index == len(tokens) - 1 and len(token) > 2 and not token.endswith("s"):
            escaped = rf"{escaped}s?"
        pieces.append(escaped)

    joined = r"[\s_\-./]*".join(pieces)
    return re.compile(rf"(?<![a-z0-9]){joined}(?![a-z0-9])", re.IGNORECASE)


_COMPILED_PATTERNS = tuple(
    pattern
    for keywords in CATEGORY_KEYWORDS.values()
    for pattern in (_keyword_to_regex(keyword) for keyword in keywords)
)


def _matches_ai_keyword(title: str, body: str) -> bool:
    haystack = f"{title or ''}\n{body or ''}".casefold()
    return any(pattern.search(haystack) for pattern in _COMPILED_PATTERNS)


def _quote_term(term: str) -> str:
    return f'"{term}"' if re.search(r"\s|\.", term) else term


def _github_queries() -> list[str]:
    since = (datetime.now(timezone.utc) - timedelta(days=GITHUB_LOOKBACK_DAYS)).date()
    queries = []

    for term in GITHUB_SEARCH_TERMS:
        safe_term = _quote_term(term)
        queries.append(
            f"{safe_term} in:name,description,readme "
            f"stars:>={GITHUB_MIN_STARS} created:>={since}"
        )

    return queries


def _headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    return headers


def _sleep_for_rate_limit(response: httpx.Response) -> None:
    retry_after = response.headers.get("Retry-After")
    reset_at = response.headers.get("X-RateLimit-Reset")

    sleep_seconds = 10

    if retry_after and retry_after.isdigit():
        sleep_seconds = int(retry_after)
    elif reset_at and reset_at.isdigit():
        sleep_seconds = max(int(reset_at) - int(time.time()) + 1, 0)

    sleep_seconds = min(sleep_seconds, GITHUB_RATE_LIMIT_MAX_SLEEP_SECONDS)
    logger.warning("GitHub rate limit hit. Sleeping for %s seconds", sleep_seconds)
    time.sleep(sleep_seconds)


def _fetch_search_page(
    client: httpx.Client,
    query: str,
    page: int,
) -> list[dict[str, Any]] | None:
    try:
        response = client.get(
            GITHUB_API_URL,
            params={
                "q": query,
                "sort": "stars",
                "order": "desc",
                "per_page": GITHUB_PER_PAGE,
                "page": page,
            },
        )

        if response.status_code in {403, 429}:
            _sleep_for_rate_limit(response)
            return None

        response.raise_for_status()
        return response.json().get("items", [])

    except httpx.HTTPStatusError:
        logger.exception("GitHub Search API failed. query=%s page=%s", query, page)
        return []
    except httpx.RequestError:
        logger.exception("GitHub request failed. query=%s page=%s", query, page)
        return []
    except Exception:
        logger.exception("Unexpected GitHub error. query=%s page=%s", query, page)
        return []


def _fetch_readme(client: httpx.Client, full_name: str) -> str:
    """레포 README 원문을 가져온다(raw 텍스트). 없거나(404) 실패하면 ''를 반환한다."""
    if not full_name:
        return ""
    try:
        response = client.get(
            f"https://api.github.com/repos/{full_name}/readme",
            headers={"Accept": "application/vnd.github.raw+json"},
        )

        if response.status_code in {403, 429}:
            _sleep_for_rate_limit(response)
            return ""
        if response.status_code == 404:
            return ""

        response.raise_for_status()
        return response.text[:GITHUB_README_MAX_CHARS]

    except (httpx.HTTPStatusError, httpx.RequestError):
        logger.warning("GitHub README fetch failed. repo=%s", full_name)
        return ""
    except Exception:
        logger.exception("Unexpected README fetch error. repo=%s", full_name)
        return ""


def _normalize_repo(repo: dict[str, Any], readme: str = "") -> ContentSchema | None:
    name = repo.get("full_name") or repo.get("name") or ""
    description = repo.get("description") or ""

    if not _matches_ai_keyword(name, description):
        return None

    # README가 있으면 설명 + README를 본문으로 합쳐 깊이를 보강한다(없으면 설명만).
    if readme:
        body = f"{description}\n\n{readme}".strip() if description else readme
    else:
        body = description

    return normalize(
        source="github_trending",
        title=name,
        url=repo.get("html_url") or "",
        body=body,
        likes=int(repo.get("stargazers_count") or 0),
        published_at=repo.get("created_at"),
    )


def collect_github(target_total: int = GITHUB_TARGET_ITEMS) -> list[ContentSchema]:
    token = os.getenv("GITHUB_TOKEN")
    max_searches = GITHUB_MAX_SEARCHES_WITH_TOKEN if token else GITHUB_MAX_SEARCHES_WITHOUT_TOKEN

    results: list[ContentSchema] = []
    seen_urls: set[str] = set()
    search_count = 0

    with httpx.Client(timeout=HTTP_TIMEOUT_SECONDS, headers=_headers()) as client:
        for query in _github_queries():
            if len(results) >= target_total or search_count >= max_searches:
                break

            empty_page_seen = False

            for page in range(1, GITHUB_MAX_PAGES_PER_QUERY + 1):
                if len(results) >= target_total or search_count >= max_searches:
                    break

                if empty_page_seen and page > GITHUB_MIN_PAGES_PER_QUERY:
                    break

                search_count += 1
                repos = _fetch_search_page(client, query, page)

                if repos is None:
                    continue

                if not repos:
                    empty_page_seen = True
                    if page >= GITHUB_MIN_PAGES_PER_QUERY:
                        break

                for repo in repos:
                    url = repo.get("html_url") or ""
                    if not url or url in seen_urls:
                        continue

                    # README는 적재 후보(미중복·AI키워드 매칭)에 한해서만 조회해 불필요한 콜을 줄인다.
                    name = repo.get("full_name") or repo.get("name") or ""
                    description = repo.get("description") or ""
                    if not _matches_ai_keyword(name, description):
                        continue

                    readme = (
                        _fetch_readme(client, name)
                        if (GITHUB_FETCH_README and token)
                        else ""
                    )

                    item = _normalize_repo(repo, readme)
                    if item is None:
                        continue

                    seen_urls.add(url)
                    results.append(item)

                    if len(results) >= target_total:
                        break

                time.sleep(GITHUB_REQUEST_SLEEP_SECONDS)

    logger.info(
        "GitHub collected %s items with %s search requests",
        len(results),
        search_count,
    )
    return results

    #11