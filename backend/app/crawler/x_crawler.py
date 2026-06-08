from __future__ import annotations

"""
HIVE-28: X seed-user crawler.

This module is intentionally self-contained:
- It reads APIFY_TOKEN from environment variables or backend/.env.
- It calls an Apify Twitter/X scraper actor through apify-client.
- It maps Apify dataset items into Dev-Hive's shared ContentSchema via normalize().
- It does not depend on config/*.json or external key files.

Operational note:
Apify Twitter/X actor input schemas vary by actor. The default input below targets
common search-based actors by querying `from:<handle>` for each seed account.
If your selected actor requires a different input schema, set
APIFY_X_RUN_INPUT_JSON to a full JSON object and this crawler will use it as-is.
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from dotenv import load_dotenv

from app.crawler.normalizer import ContentSchema, normalize

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_ROOT / ".env")

AI_KEYWORDS = [
    'Cursor AI workflow', 'building with Claude', 'RAG production issue', 'LLM fine-tuning tips', 
    'LangChain production error', 'AI Agent hackathon', 'v0.dev frontend build', 'Bolt.new review',
    'LlamaIndex optimization', 'Local LLM setup tutorial', 'VectorDB scaling issue', 'Agentic Workflow build',
    'AI coding limitations', 'Prompt engineering hacks', 'reducing LLM API cost', 'context window limit',
    'LLM pipeline breakdown', 'GraphRAG implementation', 'OpenAI API rate limit', 'Claude 3.5 Sonnet coding',
    'custom GPT development', 'v0 dev troubleshooting', 'Ollama integration issue', 'DeepSeek inference speed',
    'AI app deployment guide'
]

# Keep the actor configurable because Apify marketplace actor schemas differ.
# A searchTerms + maxItems input works with many Twitter/X scraper actors.
APIFY_X_ACTOR_ID = os.getenv("APIFY_X_ACTOR_ID", "delicious_zebu/ultimate-x-twitter-advanced-search-scraper")
APIFY_X_TARGET_TOTAL = int(os.getenv("APIFY_X_TARGET_TOTAL", "500"))
APIFY_X_BODY_MAX_CHARS = int(os.getenv("APIFY_X_BODY_MAX_CHARS", "500"))
APIFY_X_REQUEST_RETRIES = int(os.getenv("APIFY_X_REQUEST_RETRIES", "3"))
APIFY_X_RETRY_SLEEP_SECONDS = float(os.getenv("APIFY_X_RETRY_SLEEP_SECONDS", "15"))


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return datetime.now(timezone.utc)

    text = str(value)

    # Twitter-style date format: 'Fri Jun 05 15:58:29 +0000 2026'
    try:
        parsed = datetime.strptime(text, "%a %b %d %H:%M:%S %z %Y")
        return parsed
    except ValueError:
        pass

    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            parsed = datetime.fromisoformat(candidate)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    # Some Apify actors return epoch milliseconds or seconds.
    try:
        timestamp = float(text)
        if timestamp > 10_000_000_000:
            timestamp = timestamp / 1000
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    except ValueError:
        logger.debug("Could not parse X created_at value: %s", value)
        return datetime.now(timezone.utc)


def _first_value(item: dict[str, Any], keys: Iterable[str], default: Any = None) -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return default


def _author_from_item(item: dict[str, Any]) -> str | None:
    author = _first_value(item, ("author", "user", "owner", "creator"), {})
    # xtdata actors may return author as a JSON string
    if isinstance(author, str):
        try:
            parsed = json.loads(author)
            if isinstance(parsed, dict):
                author = parsed
        except (json.JSONDecodeError, TypeError):
            return author
    if isinstance(author, dict):
        return _first_value(
            author,
            ("userName", "username", "screen_name", "name", "displayName"),
        )
    return _first_value(item, ("username", "userName", "screen_name", "authorName"))


def _url_from_item(item: dict[str, Any], author_name: str | None) -> str:
    url = _first_value(item, ("url", "tweetUrl", "twitterUrl", "link", "permalink"), "")
    if url:
        return str(url)

    tweet_id = _first_value(item, ("id", "tweetId", "rest_id", "conversationId"), "")
    if tweet_id and author_name:
        return f"https://x.com/{author_name}/status/{tweet_id}"
    if tweet_id:
        return f"https://x.com/i/web/status/{tweet_id}"
    return ""


def _engagement_counts(item: dict[str, Any]) -> tuple[int, int]:
    likes = _first_value(
        item,
        ("likes", "likeCount", "favorite_count", "favoriteCount", "favorites", "bookmark_count"),
        0,
    )
    retweets = _first_value(
        item,
        ("retweets", "retweetCount", "retweet_count", "reposts", "repostCount"),
        0,
    )
    replies = _first_value(item, ("replies", "replyCount", "comments", "commentCount"), 0)

    def as_int(value: Any) -> int:
        try:
            return max(int(value or 0), 0)
        except (TypeError, ValueError):
            return 0

    # ContentSchema has likes/comments only. Retweets are added into comments as
    # an interaction proxy so downstream ranking still sees distribution signal.
    return as_int(likes), as_int(retweets) + as_int(replies)


def _clean_x_text(text: str) -> str:
    cleaned = re.sub(r"https?://\S+", "", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # ToS / copyright guardrail:
    # Do not persist the full X post body by default. Store a short excerpt and
    # keep the canonical URL so downstream AI summarization can reference the
    # original source without bulk-republishing the full text.
    if len(cleaned) > APIFY_X_BODY_MAX_CHARS:
        cleaned = cleaned[:APIFY_X_BODY_MAX_CHARS].rstrip() + "..."
    return cleaned


def _title_from_text(text: str, author_name: str | None) -> str:
    compact = _clean_x_text(text)
    if compact:
        return compact[:120]
    return f"X post by @{author_name}" if author_name else "X post"


def _build_default_actor_input(keyword: str, target_total: int) -> dict[str, Any]:
    return {
        "All_of_these_words": keyword,
        "maxItems": target_total,
        "language": "en",
        "splitMode": "day"
    }


def _actor_input(keyword: str, target_total: int) -> dict[str, Any]:
    override = os.getenv("APIFY_X_RUN_INPUT_JSON")
    if override:
        try:
            payload = json.loads(override)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            logger.exception("Invalid APIFY_X_RUN_INPUT_JSON; falling back to default input")
    return _build_default_actor_input(keyword, target_total)


def _get_apify_client():
    token = os.getenv("APIFY_TOKEN")
    if not token:
        raise RuntimeError("APIFY_TOKEN is required in backend/.env or environment variables")

    try:
        from apify_client import ApifyClient
    except ImportError as exc:
        raise RuntimeError(
            "apify-client is required. Install it with: pip install apify-client"
        ) from exc

    return ApifyClient(token)


def _run_actor_with_retries(client: Any, run_input: dict[str, Any]) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, APIFY_X_REQUEST_RETRIES + 1):
        try:
            return client.actor(APIFY_X_ACTOR_ID).call(run_input=run_input)
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Apify X actor failed attempt=%s/%s actor=%s error=%s",
                attempt,
                APIFY_X_REQUEST_RETRIES,
                APIFY_X_ACTOR_ID,
                exc,
            )
            if attempt < APIFY_X_REQUEST_RETRIES:
                time.sleep(APIFY_X_RETRY_SLEEP_SECONDS * attempt)

    raise RuntimeError(f"Apify X actor failed after retries: {last_error}") from last_error


def normalize_x_item(item: dict[str, Any]) -> ContentSchema | None:
    raw_text = str(_first_value(item, ("full_text", "text", "fullText", "body", "content"), "") or "")
    author_name = _author_from_item(item)
    url = _url_from_item(item, author_name)
    if not url:
        return None

    body = _clean_x_text(raw_text)
    likes, comments = _engagement_counts(item)
    language = str(_first_value(item, ("lang", "language", "languageCode"), "und") or "und")
    published_at = _parse_datetime(
        _first_value(item, ("createdAt", "created_at", "timestamp", "date"))
    )

    # 제목(title) 잘림 방지: body(본문)의 첫 30자만 슬라이싱한 뒤 '...'을 붙여 title 필드를 생성
    title = (body[:30] + "...") if body else "X post"

    return normalize(
        title=title,
        source="X",
        url=url,
        published_at=published_at,
        body=body,
        author_name=author_name,
        language=language,
        likes=likes,
        comments=comments,
    )


def dedupe_by_url(items: list[ContentSchema]) -> list[ContentSchema]:
    """Stage 1 dedupe: remove duplicate URLs inside a single Apify dump."""
    seen_urls: set[str] = set()
    deduped: list[ContentSchema] = []
    for item in items:
        if not item.url or item.url in seen_urls:
            continue
        seen_urls.add(item.url)
        deduped.append(item)
    return deduped


def filter_existing_urls(
    items: list[ContentSchema],
    existing_urls: set[str] | None = None,
) -> list[ContentSchema]:
    """Stage 2 dedupe: remove URLs already known by caller/DB/raw pipeline."""
    if not existing_urls:
        return items
    return [item for item in items if item.url not in existing_urls]


def collect_x_seed_users(
    seed_accounts: list[str] | None = None,
    target_total: int = APIFY_X_TARGET_TOTAL,
    existing_urls: set[str] | None = None,
) -> list[ContentSchema]:
    keywords = seed_accounts or AI_KEYWORDS
    client = _get_apify_client()
    
    # 중복 제거를 감안하여 키워드당 25건씩 수집을 목표로 함 (25 * 25 = 625건)
    per_keyword = 25
    
    logger.info(
        "Starting Apify X crawl actor=%s keywords=%s target_total=%s per_keyword=%s",
        APIFY_X_ACTOR_ID,
        keywords,
        target_total,
        per_keyword,
    )
    
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    all_normalized_items: list[ContentSchema] = []
    
    def crawl_single_keyword(kw: str) -> list[ContentSchema]:
        run_input = _actor_input(kw, per_keyword)
        kw_items = []
        try:
            run = _run_actor_with_retries(client, run_input)
            run_dict = run if isinstance(run, dict) else run.model_dump() if hasattr(run, 'model_dump') else run.__dict__
            dataset_id = run_dict.get("default_dataset_id") or run_dict.get("defaultDatasetId")
            if not dataset_id:
                return []
            
            for raw_item in client.dataset(dataset_id).iterate_items():
                try:
                    item = normalize_x_item(raw_item)
                    if item is not None:
                        kw_items.append(item)
                except Exception:
                    logger.exception("Failed to normalize X dataset item")
        except Exception as e:
            logger.error(f"Error crawling keyword '{kw}': {e}")
        return kw_items

    # 동시 실행 크기를 4 정도로 제한하여 Apify queue 병목 방지
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(crawl_single_keyword, kw): kw for kw in keywords}
        for future in as_completed(futures):
            kw = futures[future]
            try:
                kw_results = future.result()
                all_normalized_items.extend(kw_results)
                logger.info(f"Keyword '{kw}' finished. Collected {len(kw_results)} items.")
            except Exception as e:
                logger.error(f"Keyword '{kw}' future failed: {e}")

    deduped = dedupe_by_url(all_normalized_items)
    filtered = filter_existing_urls(deduped, existing_urls)
    logger.info(
        "X crawl finished raw=%s deduped=%s filtered=%s",
        len(all_normalized_items),
        len(deduped),
        len(filtered),
    )
    return filtered


if __name__ == "__main__":
    # Remove default handlers to suppress standard logging, so we only print the requested output
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")

    TARGET = 500
    OUTPUT_PATH = BACKEND_ROOT / "x_crawl_dump_500.json"

    items = collect_x_seed_users(target_total=TARGET)

    # ── 공통 규격으로 변환 (소문자 스네이크 케이스) ──
    shared_records: list[dict] = []
    for item in items:
        shared_records.append({
            "title": item.title,
            "body": item.body or "",
            "author": item.author_name or "",
            "source": "X",          # 값은 'X'로 고정
            "url": item.url,
            "created_at": item.published_at.isoformat(),
            "likes": item.engagement.get("likes", 0),
            "language": item.language,
        })

    # ── JSON 파일 저장 ──
    shared_records = shared_records[:TARGET]
    with open(OUTPUT_PATH, "w", encoding="utf-8") as fp:
        json.dump(shared_records, fp, ensure_ascii=False, indent=2)

    # ── 결과 리포트 및 검증 ──
    print("X 영문 키워드 검색 기반 500건 재수집 및 소문자 스키마 저장 완료 (✅ SUCCESS)")
    sample = shared_records[:2]
    print(json.dumps(sample, ensure_ascii=False, indent=2))
