"""HIVE-28: X 시드유저 하이브리드 크롤러 (리팩토링 v3).

self-contained:
- APIFY_TOKEN(env 또는 backend/.env)로 Apify X 스크래퍼 액터를 호출.
- SEED_USERS × KEYWORDS 하이브리드 쿼리로 시드유저의 기술 트윗만 정밀 타겟팅.
- Apify 데이터셋 항목을 공유 ContentSchema로 정규화(normalize()).

고도화 요건 반영:
  [1] Engagement 스키마 정규화 (likes/comments/retweets/views 4필드 정밀 매핑)
  [2] 인물(User) × 주제(Keyword) 하이브리드 통합 검색 쿼리 빌더 및 최적화
  [3] 정규표현식(re.sub)을 활용한 t.co 단축 URL 및 미디어 링크 클렌징
  [4] entities.urls에서 외부 expanded_url 우선 추출 및 Content.url 최우선 매핑 (fallback 포함)
  [5] 실시간 진행 상황 보고, 타임아웃 및 Rate Limit 조기 종료(Early Exit) 가드 구현
  [6] 로컬 실행 검증용 Main 블록 및 JSON 파일 저장
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
from app.crawler.qc_gate import detect_language

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_ROOT / ".env")

# ──────────────────────────────────────────────────────────────────────────────
# [요건 2] 하이브리드 수집 상수: 시드 유저 × 기술 키워드 (실제 프로젝트 마스터 플랜 기준)
# ──────────────────────────────────────────────────────────────────────────────
SEED_USERS: list[str] = [
    "karpathy", "sama", "LocalBee", "ylecun", "geoffreyhinton", 
    "AndrewYNg", "demishassabis", "gdb", "ilyasut", "fchollet", 
    "AravSrinivas", "charlie智能化", "mrkevinscott", "satyanadella"
]

KEYWORDS: list[str] = [
    "MCP", "Model Context Protocol", "Claude 5", "RAG infrastructure", 
    "LLM Guardrails", "vLLM", "GraphSAGE", "Vector DB", "B2B2C", 
    "EV Market Strategy", "Product Management", "Growth Hacking", 
    "AI Prompt Engineering", "Giga Casting", "Gigafactory"
]

APIFY_X_ACTOR_ID = os.getenv("APIFY_X_ACTOR_ID", "delicious_zebu/ultimate-x-twitter-advanced-search-scraper")
APIFY_X_TARGET_TOTAL = int(os.getenv("APIFY_X_TARGET_TOTAL", "500"))
APIFY_X_BODY_MAX_CHARS = int(os.getenv("APIFY_X_BODY_MAX_CHARS", "500"))
APIFY_X_REQUEST_RETRIES = int(os.getenv("APIFY_X_REQUEST_RETRIES", "3"))
APIFY_X_RETRY_SLEEP_SECONDS = float(os.getenv("APIFY_X_RETRY_SLEEP_SECONDS", "15"))


# ══════════════════════════════════════════════════════════════════════════════
# 유틸리티 함수
# ══════════════════════════════════════════════════════════════════════════════

def _parse_datetime(value: Any) -> datetime:
    """다양한 형태의 날짜 문자열을 datetime(tz-aware)으로 파싱."""
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
    """여러 후보 키를 순회하며 첫 번째 유효한 값을 반환."""
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return default


def _as_int(value: Any) -> int:
    """안전한 정수 변환. 음수는 0으로 클램프."""
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _to_dict(obj: Any) -> dict[str, Any]:
    """Apify Pydantic 객체 또는 기타 모델을 안전하게 딕셔너리로 변환."""
    if not obj:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return {}


# ══════════════════════════════════════════════════════════════════════════════
# [요건 3] 텍스트 클렌징: t.co 단축 URL 및 미디어 링크 제거
# ══════════════════════════════════════════════════════════════════════════════

def _strip_tco_urls(text: str) -> str:
    """트윗 본문에서 https://t.co/xxxx 형태의 X 내부 단축 URL을 모두 제거.

    LLM 태거의 토큰 낭비를 방지하고, 본문을 깔끔하게 정제한다.
    """
    if not text:
        return ""
    # [요건 3] re.sub(r'https://t\.co/\w+', '', text) 정규표현식 강제 사용
    cleaned = re.sub(r'https://t\.co/\w+', '', text)
    # 잔여 공백 정리
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _clean_x_text(text: str) -> str:
    """트윗 본문 전처리: t.co URL 제거 → 일반 URL 제거 → 공백 압축 → 길이 제한."""
    # [요건 3] t.co 단축 URL 우선 제거
    cleaned = _strip_tco_urls(text or "")
    # 나머지 일반 URL도 제거 (혹시 남은 http(s) 링크)
    cleaned = re.sub(r"https?://\S+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # ToS / copyright guardrail:
    # Do not persist the full X post body by default. Store a short excerpt and
    # keep the canonical URL so downstream AI summarization can reference the
    # original source without bulk-republishing the full text.
    if len(cleaned) > APIFY_X_BODY_MAX_CHARS:
        cleaned = cleaned[:APIFY_X_BODY_MAX_CHARS].rstrip() + "..."
    return cleaned


# ══════════════════════════════════════════════════════════════════════════════
# 작성자(Author) 추출
# ══════════════════════════════════════════════════════════════════════════════

def _author_from_item(item: dict[str, Any]) -> str | None:
    """트윗 객체에서 작성자 핸들/이름을 추출."""
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


# ══════════════════════════════════════════════════════════════════════════════
# [요건 3] 엔티티 구조 파싱을 통한 외부 아웃바운드 URL 추출
# ══════════════════════════════════════════════════════════════════════════════

# X 내부 도메인 → 외부 링크로 간주하지 않는 호스트 목록
_X_INTERNAL_HOSTS = frozenset({
    "twitter.com", "www.twitter.com",
    "x.com", "www.x.com",
    "t.co", "pic.twitter.com",
    "pbs.twimg.com", "video.twimg.com",
})


def _extract_outbound_url(item: dict[str, Any]) -> str | None:
    """entities.urls 배열에서 외부 기술 블로그/GitHub 등 아웃바운드 URL을 추출.

    외부 링크가 발견되면 expanded_url을 반환하고,
    없으면 None을 반환하여 호출부가 트윗 자체 URL을 fallback으로 사용하게 한다.
    """
    entities = item.get("entities") or {}
    urls_list = entities.get("urls") or []

    # 일부 Apify 액터는 entities가 아닌 최상위에 urls 키를 두기도 함
    if not urls_list:
        urls_list = item.get("urls") or []

    for url_entity in urls_list:
        if not isinstance(url_entity, dict):
            continue
        expanded = url_entity.get("expanded_url") or url_entity.get("expandedUrl") or ""
        if not expanded:
            continue
        # mailto: 등 비-http 스킴 제외
        if not expanded.startswith(("http://", "https://")):
            continue

        # 도메인 추출하여 X 내부 도메인인지 확인
        try:
            domain = expanded.split("//", 1)[1].split("/", 1)[0].split("?")[0].split(":")[0].lower()
            if domain.startswith("www."):
                domain = domain[4:]
            if domain not in _X_INTERNAL_HOSTS:
                return expanded
        except (IndexError, AttributeError):
            continue

    return None


def _url_from_item(item: dict[str, Any], author_name: str | None) -> str:
    """[요건 3] 외부 아웃바운드 URL을 최우선으로 사용, 없으면 트윗 URL fallback."""
    # 1순위: entities.urls에서 외부 링크 추출
    outbound_url = _extract_outbound_url(item)
    if outbound_url:
        return outbound_url

    # 2순위(fallback): 트윗 자체 URL
    url = _first_value(item, ("url", "tweetUrl", "twitterUrl", "link", "permalink"), "")
    if url:
        return str(url)

    tweet_id = _first_value(item, ("id", "tweetId", "rest_id", "conversationId"), "")
    if tweet_id and author_name:
        return f"https://x.com/{author_name}/status/{tweet_id}"
    if tweet_id:
        return f"https://x.com/i/web/status/{tweet_id}"
    return ""


# ══════════════════════════════════════════════════════════════════════════════
# [요건 1] Engagement(인게이지먼트) 스키마 정규화 및 Key 매핑 정정
# ══════════════════════════════════════════════════════════════════════════════

def _engagement_counts(raw_tweet: dict[str, Any]) -> dict[str, int]:
    """Apify 원본 데이터에서 정확한 engagement 4필드를 추출.

    기존 likes=0 일괄 적재 바인딩 오류를 해결하기 위해
    Apify 트윗 덤프의 원본 키를 명시적으로 매핑한다.
    """
    likes = _as_int(raw_tweet.get("likeCount", 0))
    comments = _as_int(raw_tweet.get("replyCount", 0))
    retweets = _as_int(raw_tweet.get("retweetCount", 0)) + _as_int(raw_tweet.get("quoteCount", 0))
    views = _as_int(raw_tweet.get("viewCount", 0))

    return {
        "likes": likes,
        "comments": comments,
        "retweets": retweets,
        "views": views,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 콘텐츠 필터링 (인사이트 키워드 기반)
# ══════════════════════════════════════════════════════════════════════════════

# 개발 팁/인사이트/경험 등 AI·기술 주제 필터용 키워드.
INSIGHT_KEYWORDS = (
    "tip", "tutorial", "how to", "guide", "experience", "insight", "learn", "hacks",
    "api", "model", "code", "coding", "llm", "rag", "agent", "mcp", "prompt", "scaling",
    "deploy", "error", "build", "run", "vector", "embedding", "dataset", "developer", "dev",
    "git", "github", "python", "ai", "expert",
)
# 단어경계 매칭 — 부분문자열 오탐 방지
_INSIGHT_PATTERN = re.compile(
    r"(?<![a-z0-9])(?:" + "|".join(re.escape(k) for k in INSIGHT_KEYWORDS) + r")(?![a-z0-9])",
    re.IGNORECASE,
)


def _is_valid_insight_tweet(text: str) -> bool:
    """단순 리트윗, 짧은 일상글, 비기술 트윗을 필터링."""
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


def _title_from_text(text: str, author_name: str | None) -> str:
    """트윗 본문에서 제목을 생성."""
    compact = _clean_x_text(text)
    if compact:
        return compact[:120]
    return f"X post by @{author_name}" if author_name else "X post"


# ══════════════════════════════════════════════════════════════════════════════
# 정규화 (Normalize): 단일 트윗 → ContentSchema
# ══════════════════════════════════════════════════════════════════════════════

def normalize_x_item(item: dict[str, Any]) -> ContentSchema | None:
    """Apify 원본 트윗 딕셔너리를 ContentSchema로 정규화.

    [요건 1] engagement 4필드 정확 매핑
    [요건 3] t.co 단축 URL 클렌징
    [요건 3] entities.urls 외부 링크 우선 추출
    """
    raw_text = str(_first_value(item, ("full_text", "text", "fullText", "body", "content"), "") or "")

    # 단순 링크 리트윗, 짧은 일상글 등 필터링 레이어
    if not _is_valid_insight_tweet(raw_text):
        return None

    author_name = _author_from_item(item)
    url = _url_from_item(item, author_name)
    if not url:
        return None

    # [요건 3] t.co URL 클렌징 적용된 본문
    body = _clean_x_text(raw_text)

    # [요건 1] Engagement 4필드 정규화
    engagement = _engagement_counts(item)

    language = str(_first_value(item, ("lang", "language", "languageCode"), "") or "")
    if language.lower() in ("", "und", "zxx", "qme", "qam"):
        language = detect_language(body) or "und"
    published_at = _parse_datetime(
        _first_value(item, ("createdAt", "created_at", "timestamp", "date"))
    )

    title = _title_from_text(raw_text, author_name)

    return ContentSchema(
        title=title,
        source="x",
        url=url,
        published_at=published_at,
        body=body,
        author_name=author_name,
        language=language,
        engagement={
            "likes": engagement["likes"],
            "comments": engagement["comments"],
            "retweets": engagement["retweets"],
            "views": engagement["views"],
        },
    )


# ══════════════════════════════════════════════════════════════════════════════
# 중복 제거
# ══════════════════════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════════════════════
# [요건 2] Apify 액터 호출 인프라 및 하이브리드 최적화 쿼리 빌더
# ══════════════════════════════════════════════════════════════════════════════

def _build_hybrid_actor_input(users: list[str], keywords: list[str], max_items: int) -> dict[str, Any]:
    """[요건 2] (from:유저 OR from:유저) (키워드 OR 키워드) 형태의 하이브리드 검색 쿼리 생성 (OR 최적화).

    여러 유저와 여러 키워드를 단일 쿼리로 대종합하여 단 1회(또는 최소한)의 API 호출로 대량 수집한다.
    """
    # X handle 규칙: 알파벳, 숫자, 언더스코어(_)만 허용.
    # charlie智能化 등 한글/중국어/특수문자가 들어간 핸들은 X 검색 쿼리 파싱 에러를 유발하므로 필터링.
    allowed_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")
    valid_users = [u for u in users if all(c in allowed_chars for c in u)]
    users_str = " ".join(valid_users)

    kw_parts = [f'"{kw}"' if " " in kw else kw for kw in keywords]
    keywords_query = f'({" OR ".join(kw_parts)})'

    # ⚠️ startDate/endDate 지정 시 최근 트윗 접근에 로그인 세션이 필요하여 404 무한 정지.
    # 날짜 미지정이 유일하게 성공 확인된 조합 — 환경변수로만 선택적으로 활성화.
    result: dict[str, Any] = {
        "All_of_these_words": keywords_query,
        "From_these_accounts": users_str,
        "maxItems": max_items,
        "language": "en",
        "proxyConfiguration": {"useApifyProxy": True},
    }
    start_date = os.getenv("APIFY_X_START_DATE")
    end_date = os.getenv("APIFY_X_END_DATE")
    if start_date:
        result["startDate"] = start_date
    if end_date:
        result["endDate"] = end_date
    return result


def _actor_input_override() -> dict[str, Any] | None:
    """환경변수 APIFY_X_RUN_INPUT_JSON이 설정되어 있으면 해당 JSON을 반환."""
    override = os.getenv("APIFY_X_RUN_INPUT_JSON")
    if override:
        try:
            payload = json.loads(override)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            logger.exception("Invalid APIFY_X_RUN_INPUT_JSON; falling back to default input")
    return None


def _get_apify_client():
    """Apify 클라이언트 초기화. APIFY_TOKEN 필수."""
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


# ══════════════════════════════════════════════════════════════════════════════
# [요건 4] 실시간 진행 상황 보고 및 타임아웃/Rate Limit 조기 종료 가드 구현
# ══════════════════════════════════════════════════════════════════════════════

def collect_x(
    seed_users: list[str] | None = None,
    keywords: list[str] | None = None,
    target_total: int = APIFY_X_TARGET_TOTAL,
    existing_urls: set[str] | None = None,
) -> list[ContentSchema]:
    """SEED_USERS × KEYWORDS 하이브리드 수집 (단일 쿼리 OR 최적화 및 조기 종료 가드 내장).

    (from:유저1 OR from:유저2 ...) (키워드1 OR 키워드2 ...) 구조의 대종합 쿼리를
    단 한 번의 요청으로 실행하고, 진행 상황을 실시간 모니터링하며
    Rate Limit 이나 네트워크 지연 발생 시 안전하게 조기 중단(Early Exit)한다.
    """
    users = seed_users or SEED_USERS
    kws = keywords or KEYWORDS
    client = _get_apify_client()

    # 환경변수 오버라이드 확인
    input_override = _actor_input_override()

    # 1. 쿼리 빌드 단계 로깅
    print("🚀 [1/4] 쿼리 빌드 완료")
    run_input = input_override or _build_hybrid_actor_input(users, kws, target_total)
    query_str = run_input.get("All_of_these_words", "N/A")
    accounts_str = run_input.get("From_these_accounts", "N/A")
    print(f"   - 검색 키워드: {query_str}")
    print(f"   - 대상 계정들: {accounts_str}")
    print(f"   - 최대 수집 목표: {target_total} 건")

    # 2. 스크레이퍼 요청 송신
    print("📡 [2/4] 스크레이퍼 요청 송신...")
    logger.info("Sending run request to Apify actor %s with keywords: %s, accounts: %s", APIFY_X_ACTOR_ID, query_str, accounts_str)
    
    last_error: Exception | None = None
    for attempt in range(1, APIFY_X_REQUEST_RETRIES + 1):
        try:
            run = client.actor(APIFY_X_ACTOR_ID).start(run_input=run_input)
            last_error = None
            break
        except Exception as exc:
            last_error = exc
            logger.warning("Apify actor start failed attempt=%d/%d: %s", attempt, APIFY_X_REQUEST_RETRIES, exc)
            if attempt < APIFY_X_REQUEST_RETRIES:
                time.sleep(APIFY_X_RETRY_SLEEP_SECONDS * attempt)
    if last_error is not None:
        print(f"   ❌ 액터 호출 실패 (재시도 {APIFY_X_REQUEST_RETRIES}회): {last_error}")
        raise RuntimeError(f"Apify actor start failed after retries: {last_error}") from last_error

    run_dict = _to_dict(run)
    run_id = run_dict.get("id")
    dataset_id = run_dict.get("defaultDatasetId") or run_dict.get("default_dataset_id")
    if not run_id or not dataset_id:
        raise RuntimeError(f"Apify actor start returned no run_id or dataset_id: {run_dict}")
    print(f"   - 액터 실행 시작 (Run ID: {run_id}, Dataset ID: {dataset_id})")

    # 3. 데이터 수집 단계 및 실시간 모니터링/조기 종료 가드
    print("📥 [3/4] 데이터 수집 중 및 모니터링...")
    
    start_time = time.time()
    last_count = 0
    last_change_time = time.time()
    consecutive_errors = 0
    MAX_CONSECUTIVE_ERRORS = 5

    # 조기 중단 설정
    stagnant_timeout = float(os.getenv("APIFY_X_STAGNANT_TIMEOUT", "90"))
    global_timeout = float(os.getenv("APIFY_X_GLOBAL_TIMEOUT", "1200"))

    while True:
        elapsed = time.time() - start_time

        try:
            run_status = _to_dict(client.run(run_id).get())
            status = run_status.get("status")

            dataset_info = _to_dict(client.dataset(dataset_id).get())
            current_count = dataset_info.get("itemCount") or dataset_info.get("item_count") or 0
            consecutive_errors = 0
        except Exception as e:
            consecutive_errors += 1
            logger.warning("Polling error #%d: %s", consecutive_errors, e)
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                logger.error("연속 %d회 폴링 실패 — 수집 중단", consecutive_errors)
                break
            status = "RUNNING"
            current_count = last_count

        # [수집 진행률: X / 500 건 완료 (Y%)] 실시간 진척도 출력
        pct = min(100, int((current_count / target_total) * 100))
        print(f"   [수집 진행률: {current_count} / {target_total} 건 완료 ({pct}%)] (경과 시간: {int(elapsed)}초, 상태: {status})")
        
        if current_count > last_count:
            last_count = current_count
            last_change_time = time.time()
            
        # 정상 완료 조건
        if status in ("SUCCEEDED", "FAILED", "TIMED_OUT", "ABORTED"):
            print(f"   - 액터 실행 종료 (최종 상태: {status})")
            break
            
        # Rate Limit / 네트워크 병목 우회 가드 (90초간 수집 정체 및 데이터가 일부라도 존재할 때)
        if time.time() - last_change_time > stagnant_timeout and current_count > 0:
            print(f"\n   ⚠️ [우회 가드] {int(stagnant_timeout)}초 동안 수집량이 증가하지 않아 작업을 안전하게 중단(Early Exit)합니다. (현재 수집된 {current_count}건 보존)")
            try:
                client.run(run_id).abort()
            except Exception:
                pass
            break
            
        # 전체 타임아웃 가드 (20분)
        if elapsed > global_timeout:
            print(f"\n   ⚠️ [우회 가드] 최대 실행 시간({int(global_timeout)}초)을 초과하여 작업을 조기 종료합니다. (현재 수집된 {current_count}건 보존)")
            try:
                client.run(run_id).abort()
            except Exception:
                pass
            break
            
        time.sleep(10)

    # 4. 정규화 및 전처리 단계
    print("🧹 [4/4] 정규화 및 전처리 시작...")
    all_normalized_items: list[ContentSchema] = []
    raw_items: list = []

    try:
        raw_items = list(client.dataset(dataset_id).iterate_items())
        total_raw = len(raw_items)
        print(f"   - 원본 데이터 총 {total_raw}건 로드 완료. 필터링 및 스키마 정규화 진행 중...")
        
        for raw_item in raw_items:
            try:
                item = normalize_x_item(raw_item)
                if item is not None:
                    all_normalized_items.append(item)
                    
                    # 정규화 진행률 출력
                    count = len(all_normalized_items)
                    pct = min(100, int((count / target_total) * 100))
                    if count % 20 == 0 or count == target_total:
                        print(f"   [정규화 진행률: {count} / {target_total} 건 완료 ({pct}%)]")
            except Exception:
                logger.exception("Failed to normalize X dataset item")
                
    except Exception as exc:
        print(f"   ❌ 데이터셋 가져오기 실패: {exc}")
        logger.error("Error reading items from dataset %s: %s", dataset_id, exc)

    # 중복 제거 및 필터링
    deduped = dedupe_by_url(all_normalized_items)
    filtered = filter_existing_urls(deduped, existing_urls)
    
    print(f"\n✅ 수집/정제 완료: 원본 {len(raw_items)}건 -> 정규화 통과 {len(all_normalized_items)}건 -> 최종 {len(filtered)}건 (중복 제거 및 기존 URL 제외)")
    logger.info(
        "X crawl finished. raw=%d normalized=%d deduped=%d filtered=%d",
        len(raw_items),
        len(all_normalized_items),
        len(deduped),
        len(filtered),
    )
    return filtered


# 하위 호환: 기존 collect_x_seed_users 함수를 호출하는 코드가 있을 수 있으므로 별칭 유지
def collect_x_seed_users(
    seed_accounts: list[str] | None = None,
    target_total: int = APIFY_X_TARGET_TOTAL,
    existing_urls: set[str] | None = None,
) -> list[ContentSchema]:
    """하위 호환 래퍼: 기존 collect_x_seed_users → collect_x 위임."""
    return collect_x(
        seed_users=seed_accounts,
        keywords=KEYWORDS,
        target_total=target_total,
        existing_urls=existing_urls,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 키워드 글로벌 검색 (from:user 제한 없이 키워드만으로 X 전체 검색) - 보조용으로 유지
# ══════════════════════════════════════════════════════════════════════════════

def _build_keyword_actor_input(keyword: str, max_items: int) -> dict[str, Any]:
    """키워드 단독 검색 쿼리 생성 (from:user 제한 없음)."""
    keyword_query = f'"{keyword}"' if " " in keyword else keyword

    return {
        "All_of_these_words": keyword_query,
        "maxItems": max_items,
        "language": "en",
        "proxyConfiguration": {"useApifyProxy": True},
    }


def collect_x_by_keywords(
    keywords: list[str] | None = None,
    target_total: int = APIFY_X_TARGET_TOTAL,
    existing_urls: set[str] | None = None,
) -> list[ContentSchema]:
    """키워드 글로벌 검색으로 대량 수집 (보조용 유지)."""
    kws = keywords or KEYWORDS
    client = _get_apify_client()

    # 키워드당 수집 목표
    per_keyword = int(os.getenv("APIFY_X_PER_KEYWORD", "0")) or max(
        50, -(-int(target_total * 1.5) // len(kws))
    )

    logger.info(
        "Starting Apify X keyword-global crawl actor=%s keywords=%d per_keyword=%d target_total=%d",
        APIFY_X_ACTOR_ID,
        len(kws),
        per_keyword,
        target_total,
    )

    all_normalized_items: list[ContentSchema] = []

    for idx, keyword in enumerate(kws, 1):
        kw_items: list[ContentSchema] = []

        try:
            # override는 루프마다 재평가 — keyword별로 독립 입력을 보장
            run_input = _actor_input_override() or _build_keyword_actor_input(keyword, per_keyword)
            query_str = run_input.get("All_of_these_words", "N/A")

            print(f"\n[{idx}/{len(kws)}] 키워드 '{keyword}' 크롤링 시작… (query: {query_str}, maxItems: {per_keyword})")
            
            # API호출은 단발성으로 처리하되, 호출 로직은 기존 _run_actor_with_retries 사용
            run = client.actor(APIFY_X_ACTOR_ID).call(
                run_input=run_input,
                run_timeout=timedelta(seconds=180),
                wait_duration=timedelta(seconds=200),
            )
            run_dict = (
                run
                if isinstance(run, dict)
                else run.model_dump() if hasattr(run, "model_dump")
                else run.__dict__
            )
            dataset_id = run_dict.get("defaultDatasetId") or run_dict.get("default_dataset_id")
            if not dataset_id:
                logger.warning("No dataset_id returned for keyword '%s'", keyword)
                continue

            raw_count = 0
            for raw_item in client.dataset(dataset_id).iterate_items():
                raw_count += 1
                try:
                    item = normalize_x_item(raw_item)
                    if item is not None:
                        kw_items.append(item)
                except Exception:
                    logger.exception("Failed to normalize X dataset item for keyword '%s'", keyword)

            all_normalized_items.extend(kw_items)
            print(f"[{idx}/{len(kws)}] 키워드 '{keyword}' 완료 → raw {raw_count}건 중 {len(kw_items)}건 정규화 통과")

        except Exception as exc:
            logger.error("Error crawling keyword '%s': %s", keyword, exc)
            print(f"[{idx}/{len(kws)}] 키워드 '{keyword}' 에러 발생: {exc}")

    deduped = dedupe_by_url(all_normalized_items)
    filtered = filter_existing_urls(deduped, existing_urls)
    return filtered


# ══════════════════════════════════════════════════════════════════════════════
# [요건 5] 로컬 실행 검증용 Main 블록
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    OUTPUT_PATH = "x_crawl_result_test.json"

    # .env 파일 로드
    try:
        from dotenv import load_dotenv as _load_env
        _load_env()
    except ImportError:
        pass

    TARGET = 500

    print("=" * 60)
    print("X 시드 유저 × 기술 키워드 하이브리드 크롤러 — 대량 수집 모드")
    print(f"  시드 유저 수: {len(SEED_USERS)}")
    print(f"  검색 키워드 수: {len(KEYWORDS)}")
    print(f"  목표 수집량: {TARGET}")
    print("=" * 60)

    try:
        # 1단계: 하이브리드 결합 수집 구동 (시드 유저들의 고품질 기술 트윗)
        print("\n=== [1단계] 시드 유저 하이브리드 크롤링 시작 ===")
        items = collect_x(
            seed_users=SEED_USERS,
            keywords=KEYWORDS,
            target_total=TARGET,
        )

        # 2단계: 목표량(500건) 미달 시 글로벌 키워드 수집으로 보충
        if len(items) < TARGET:
            needed = TARGET - len(items)
            print(f"\n⚠️  하이브리드 수집 결과({len(items)}건)가 목표 수량({TARGET}건)에 미달합니다.")
            print(f"=== [2단계] 글로벌 키워드 크롤링 시작 (부족분 {needed}건 추가 수집) ===")
            
            # 수집된 기존 URL 목록을 전달하여 중복 수집 방지
            existing_urls = {item.url for item in items if item.url}
            
            # 10개 핵심 키워드로 글로벌 검색 수행
            SEARCH_KEYWORDS = [
                "MCP", "Claude Code", "RAG", "LLM agent", "vLLM",
                "LangChain", "AI coding", "open source LLM", "prompt engineering", "vector database"
            ]
            global_items = collect_x_by_keywords(
                keywords=SEARCH_KEYWORDS,
                target_total=needed,
                existing_urls=existing_urls
            )
            items.extend(global_items)
            print(f"✅ 글로벌 키워드 추가 수집 완료: +{len(global_items)}건 (총 {len(items)}건)")

        # 표준 ContentSchema로 덤프
        shared_records = [item.model_dump(mode="json") for item in items]

        if not shared_records:
            print(f"\n⚠️  수집된 항목이 없습니다. 기존 {OUTPUT_PATH} 파일을 보호하기 위해 저장을 건너뜁니다.")
        else:
            # [요건 5] JSON 파일로 저장
            with open(OUTPUT_PATH, "w", encoding="utf-8") as fp:
                json.dump(shared_records, fp, ensure_ascii=False, indent=4)

            print(f"\n✅ 성공적으로 {OUTPUT_PATH} 파일로 저장되었습니다. (총 {len(shared_records)}개)")

            # 통계 출력
            total_likes = sum(r["engagement"].get("likes", 0) for r in shared_records)
            total_views = sum(r["engagement"].get("views", 0) for r in shared_records)
            authors = set(r["author_name"] for r in shared_records if r.get("author_name"))
            print(f"   📊 총 좋아요: {total_likes:,} | 총 조회수: {total_views:,} | 고유 작성자: {len(authors)}명")

            # 첫 3건만 미리보기 출력
            print("\n── 미리보기 (첫 3건) ──")
            for rec in shared_records[:3]:
                print(json.dumps(rec, ensure_ascii=False, indent=2))

    except Exception as e:
        logger.exception("로컬 실행 중 에러 발생")
        print(f"\n❌ 실행 중 에러 발생: {e}")
        raise
