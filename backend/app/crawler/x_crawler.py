"""HIVE-28: X 시드유저 크롤러.

self-contained:
- APIFY_TOKEN(env 또는 backend/.env)로 Apify X 스크래퍼 액터를 호출.
- 14인 전문가 계정을 `from:<handle>`로 시드유저 크롤(키워드 검색 아님).
- Apify 데이터셋 항목을 공유 ContentSchema로 정규화(normalize()).

적재 흐름(X는 일회성 Apify라 스케줄러에 등록하지 않는다):
  1) python -m app.crawler.x_crawler  →  표준 ContentSchema JSON 덤프
  2) python scripts/run_tagging_pipeline.py <json>
     → QC게이트가 source="x"를 허용(HIVE-28) → 태깅→가공→임베딩→적재.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Iterable

from dotenv import load_dotenv

from app.crawler.normalizer import ContentSchema, normalize

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_ROOT / ".env")

TARGET_USERS = [
    'marcusyul', 'HowToAI', 'swyx', 'charles_irl',
    'HamelHusain', 'hwchase17', 'jerryjliu0', 'clancynewman',
    'maxwoolf', 'jxnlco', 'reach_vb', 'deepfates', 'transitive_bs',
    'karpathy',  # 마지막으로 이동 (스크래핑 난이도 높음)
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
    # 기본값을 None으로(과거 {}는 dict라 아래 top-level 폴백을 막아 author가 누락됐다).
    author = _first_value(item, ("author", "user", "owner", "creator"))
    # xtdata actors may return author as a JSON string
    if isinstance(author, str):
        try:
            parsed = json.loads(author)
            if isinstance(parsed, dict):
                author = parsed
        except (json.JSONDecodeError, TypeError):
            return author
    if isinstance(author, dict) and author:
        name = _first_value(
            author,
            ("userName", "username", "screen_name", "name", "displayName"),
        )
        if name:
            return name
    # top-level 폴백(author가 중첩 dict가 아니라 최상위 username 등으로 오는 액터)
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


def _build_default_actor_input(user: str, target_total: int) -> dict[str, Any]:
    # ⚠️ startDate/endDate 를 지정하면 최근 트윗 접근 시 로그인 세션이
    #    필요하여 404에서 무한 정지합니다.
    # → 날짜 미지정 시 액터가 자체 기본값(2025-10-~)으로 검색하며,
    #   이 방식이 유일하게 성공 확인된 조합입니다.
    return {
        "All_of_these_words": f"from:{user}",
        "maxItems": target_total,
        "language": "en",
        "proxyConfiguration": {"useApifyProxy": True},
    }


def _actor_input(user: str, target_total: int) -> dict[str, Any]:
    override = os.getenv("APIFY_X_RUN_INPUT_JSON")
    if override:
        try:
            payload = json.loads(override)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            logger.exception("Invalid APIFY_X_RUN_INPUT_JSON; falling back to default input")
    return _build_default_actor_input(user, target_total)


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
            # run_timeout: Apify 서버에서 액터를 최대 3분 실행 후 강제 종료.
            # wait_duration: 우리 코드가 결과를 기다리는 최대 시간 (무한 정지 방지).
            return client.actor(APIFY_X_ACTOR_ID).call(
                run_input=run_input,
                run_timeout=timedelta(seconds=180),
                wait_duration=timedelta(seconds=200),
            )
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


# 개발 팁/인사이트/경험 등 AI·기술 주제 필터용 키워드.
INSIGHT_KEYWORDS = (
    "tip", "tutorial", "how to", "guide", "experience", "insight", "learn", "hacks",
    "api", "model", "code", "coding", "llm", "rag", "agent", "mcp", "prompt", "scaling",
    "deploy", "error", "build", "run", "vector", "embedding", "dataset", "developer", "dev",
    "git", "github", "python", "ai", "expert",
)
# 단어경계 매칭 — 부분문자열 오탐 방지("ai"가 said/email/again, "dev"가 device, "run"이 running에
# 걸리는 것을 막는다). github_crawler._keyword_to_regex와 동일한 경계 패턴.
_INSIGHT_PATTERN = re.compile(
    r"(?<![a-z0-9])(?:" + "|".join(re.escape(k) for k in INSIGHT_KEYWORDS) + r")(?![a-z0-9])",
    re.IGNORECASE,
)


def _is_valid_insight_tweet(text: str) -> bool:
    # 1. RT(리트윗) 패턴 및 단순 링크 리트윗 제외
    if text.startswith("RT @") or text.strip().startswith("RT "):
        return False

    # 2. 본문 텍스트 정리 (URL 등 제거 후의 실제 텍스트)
    cleaned = re.sub(r"https?://\S+", "", text).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # 3. 짧은 일상글 제외 (실질 본문이 25자 미만)
    if len(cleaned) < 25:
        return False

    # 4. 단순 링크만 포함한 트윗 제외 (정리 후 남은 글이 없거나 특수문자만 남은 경우)
    if not re.search(r"[a-zA-Z가-힣0-9]", cleaned):
        return False

    # 5. AI/기술 주제 키워드를 단어경계로 매칭(오탐 방지)
    if not _INSIGHT_PATTERN.search(text):
        return False

    return True


def normalize_x_item(item: dict[str, Any]) -> ContentSchema | None:
    raw_text = str(_first_value(item, ("full_text", "text", "fullText", "body", "content"), "") or "")
    
    # 단순 링크 리트윗, 짧은 일상글 등 필터링 레이어
    if not _is_valid_insight_tweet(raw_text):
        return None

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

    title = _title_from_text(raw_text, author_name)

    return normalize(
        title=title,
        source="x",  # 소스 필드 명은 무조건 "x"로 고정
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
    users = seed_accounts or TARGET_USERS
    client = _get_apify_client()

    # 계정당 수집 목표를 target_total에서 도출(파라미터가 실제 볼륨을 제어하도록).
    # 예: target_total=500, 14명 → 36건/명. APIFY_X_PER_USER로 직접 지정 가능.
    per_user = int(os.getenv("APIFY_X_PER_USER", "0")) or max(
        1, -(-target_total // len(users))
    )

    logger.info(
        "Starting Apify X crawl (sequential) actor=%s users=%s target_total=%s per_user=%s",
        APIFY_X_ACTOR_ID,
        users,
        target_total,
        per_user,
    )

    all_normalized_items: list[ContentSchema] = []

    # ── 순차(Sequential) 실행 ──────────────────────────────────────────
    # 동시에 여러 액터를 실행하면 Apify 무료 플랜의 메모리 한도(8 192 MB)를
    # 초과하므로, 한 번에 딱 하나의 액터만 실행하고 완료 후 다음 유저로 넘어갑니다.
    # (액터 1개 기본 메모리 = 1 024 MB → 한도 내 안전)
    for user in users:
        run_input = _actor_input(user, per_user)
        user_items: list[ContentSchema] = []
        try:
            print(f"[{user}] 크롤링 시작…")
            run = _run_actor_with_retries(client, run_input)
            run_dict = (
                run
                if isinstance(run, dict)
                else run.model_dump() if hasattr(run, "model_dump")
                else run.__dict__
            )
            dataset_id = run_dict.get("defaultDatasetId") or run_dict.get("default_dataset_id")
            if not dataset_id:
                logger.warning("No dataset_id returned for user '%s'", user)
                continue

            for raw_item in client.dataset(dataset_id).iterate_items():
                try:
                    item = normalize_x_item(raw_item)
                    if item is not None:
                        user_items.append(item)
                except Exception:
                    logger.exception("Failed to normalize X dataset item")

            all_normalized_items.extend(user_items)
            print(f"[{user}] 완료 → {len(user_items)}건 수집")
            logger.info("User '%s' finished. Collected %s items.", user, len(user_items))

        except Exception as exc:
            logger.error("Error crawling user '%s': %s", user, exc)
            print(f"[{user}] 에러 발생: {exc}")

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
    OUTPUT_PATH = "x_trending_only.json"

    # .env 파일 로드
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    items = collect_x_seed_users(target_total=TARGET)

    # 표준 ContentSchema로 덤프(다른 크롤러와 동일 포맷) → run_tagging_pipeline이 바로 적재 가능.
    # (이전엔 author/created_at/likes 커스텀 키라 파이프라인 스키마와 불일치했음)
    shared_records = [item.model_dump(mode="json") for item in items][:TARGET]

    if not shared_records:
        print(f"\n⚠️  수집된 항목이 없습니다. 기존 {OUTPUT_PATH} 파일을 보호하기 위해 저장을 건너뜁니다.")
        print("   → Apify 프록시 세션이 소진되었을 수 있습니다. 30~60분 후 재시도하세요.")
    else:
        # ── 콘솔에 예쁘게 출력 ──
        pretty_json = json.dumps(shared_records, indent=2, ensure_ascii=False)
        print(pretty_json)

        try:
            with open(OUTPUT_PATH, "w", encoding="utf-8") as fp:
                fp.write(pretty_json)
            print(f"\n성공적으로 {OUTPUT_PATH} 파일로 저장되었습니다. (총 {len(shared_records)}개)")
        except Exception as e:
            print(f"\n파일 저장 중 오류가 발생했습니다: {e}")

