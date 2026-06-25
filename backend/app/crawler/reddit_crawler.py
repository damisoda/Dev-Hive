from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import praw
import prawcore

from app.crawler.normalizer import ContentSchema, normalize

logger = logging.getLogger(__name__)

REDDIT_LOOKBACK_DAYS = int(os.getenv("REDDIT_LOOKBACK_DAYS", "7"))
REDDIT_LIMIT_PER_LISTING = int(os.getenv("REDDIT_LIMIT_PER_LISTING", "300"))
REDDIT_REQUEST_SLEEP_SECONDS = float(os.getenv("REDDIT_REQUEST_SLEEP_SECONDS", "1.0"))
REDDIT_PRAW_MIN_BODY = int(os.getenv("REDDIT_PRAW_MIN_BODY", "300"))

DEFAULT_SUBREDDITS = [
    "MachineLearning",
    "LocalLLaMA",
    "LocalLLM",
    "ArtificialIntelligence",
    "ArtificialInteligence",
    "LangChain",
    "OpenAI",
    "ChatGPT",
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


def _build_reddit_client() -> praw.Reddit | None:
    required = ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        logger.warning("Reddit crawler skipped. Missing credentials: %s", ", ".join(missing))
        return None

    reddit = praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        user_agent=os.environ["REDDIT_USER_AGENT"],
    )
    reddit.read_only = True
    return reddit


def _normalize_post(post: Any) -> ContentSchema | None:
    title = post.title or ""
    body = post.selftext or ""

    if not _matches_ai_keyword(title, body):
        return None

    if len(body) < REDDIT_PRAW_MIN_BODY:
        logger.debug("body 짧아 제외 (%d자): %s", len(body), getattr(post, "permalink", ""))
        return None

    return normalize(
        source="reddit",
        title=title,
        url=f"https://www.reddit.com{post.permalink}",
        body=body,
        likes=int(post.score or 0),
        comments=int(post.num_comments or 0),
        published_at=datetime.fromtimestamp(
            float(post.created_utc), tz=timezone.utc
        ).isoformat(),
    )


def collect_reddit(
    subreddit_names: list[str] | tuple[str, ...] | None = None,
    target_total: int = 600,
) -> list[ContentSchema]:
    reddit = _build_reddit_client()
    if reddit is None:
        return []

    subreddits = list(subreddit_names or DEFAULT_SUBREDDITS)
    cutoff = datetime.now(timezone.utc) - timedelta(days=REDDIT_LOOKBACK_DAYS)

    results: list[ContentSchema] = []
    seen_urls: set[str] = set()

    for subreddit_name in subreddits:
        if len(results) >= target_total:
            break

        try:
            subreddit = reddit.subreddit(subreddit_name)
        except Exception:
            logger.exception("Failed to open subreddit: r/%s", subreddit_name)
            continue

        listings = (
            ("hot", lambda: subreddit.hot(limit=REDDIT_LIMIT_PER_LISTING)),
            ("top_week", lambda: subreddit.top(time_filter="week", limit=REDDIT_LIMIT_PER_LISTING)),
        )

        for listing_name, listing_getter in listings:
            if len(results) >= target_total:
                break

            try:
                for post in listing_getter():
                    try:
                        created_at = datetime.fromtimestamp(
                            float(post.created_utc), tz=timezone.utc
                        )
                        if created_at < cutoff:
                            continue

                        url = f"https://www.reddit.com{post.permalink}"
                        if url in seen_urls:
                            continue

                        item = _normalize_post(post)
                        if item is None:
                            continue

                        seen_urls.add(url)
                        results.append(item)

                        if len(results) >= target_total:
                            break

                    except Exception:
                        logger.exception(
                            "Failed to parse Reddit post from r/%s %s",
                            subreddit_name,
                            listing_name,
                        )

                time.sleep(REDDIT_REQUEST_SLEEP_SECONDS)

            except prawcore.exceptions.RequestException:
                logger.exception("Reddit request failed: r/%s %s", subreddit_name, listing_name)
                time.sleep(min(REDDIT_REQUEST_SLEEP_SECONDS * 5, 30))
            except prawcore.exceptions.ResponseException:
                logger.exception("Reddit response error: r/%s %s", subreddit_name, listing_name)
                time.sleep(min(REDDIT_REQUEST_SLEEP_SECONDS * 5, 30))
            except prawcore.exceptions.ServerError:
                logger.exception("Reddit server error: r/%s %s", subreddit_name, listing_name)
                time.sleep(min(REDDIT_REQUEST_SLEEP_SECONDS * 10, 60))
            except Exception:
                logger.exception("Failed to collect Reddit listing: r/%s %s", subreddit_name, listing_name)
                time.sleep(min(REDDIT_REQUEST_SLEEP_SECONDS * 5, 30))

    logger.info("Reddit collected %s items", len(results))
    return results