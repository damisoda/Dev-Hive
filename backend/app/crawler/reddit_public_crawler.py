"""
Reddit 경험담 크롤러 — Arctic Shift 공개 아카이브 API 사용.
인증 불필요. www.reddit.com이 한국 네트워크에서 막힐 때 대안.
입문·중급 경험담에 특화된 서브레딧과 필터 적용.

Arctic Shift 주의사항:
- score, num_comments: 아카이빙 시점 값이라 0~1 고정. 필터 기준으로 쓰지 않음.
- 422: 시간 범위가 너무 좁으면 발생. 최소 1시간 간격으로 페이지네이션 종료.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone

import requests

from app.crawler.normalizer import ContentSchema, normalize

logger = logging.getLogger(__name__)

REDDIT_LOOKBACK_DAYS = int(os.getenv("REDDIT_LOOKBACK_DAYS", "365"))
REDDIT_REQUEST_SLEEP = float(os.getenv("REDDIT_REQUEST_SLEEP", "1.0"))
REDDIT_MIN_BODY      = int(os.getenv("REDDIT_MIN_BODY", "500"))
REDDIT_PAGE_SIZE     = int(os.getenv("REDDIT_PAGE_SIZE", "100"))

# 대형 서브레딧은 밈·감탄글 노이즈가 많아 더 높은 최소 본문 길이 적용
_SUBREDDIT_MIN_BODY: dict[str, int] = {
    "ChatGPT": 600,
    "ArtificialIntelligence": 800,
    "OpenAI": 700,
}

_API     = "https://arctic-shift.photon-reddit.com/api/posts/search"
_HEADERS = {"User-Agent": "dev-hive-crawler/1.0"}
_MIN_WINDOW = timedelta(hours=1)  # 이것보다 좁은 범위는 422 유발

# .env의 BEGINNER_SUBREDDITS (쉼표 구분) 로 관리 — 코드에 하드코딩 금지
BEGINNER_SUBREDDITS: list[str] = [
    s.strip()
    for s in os.getenv(
        "BEGINNER_SUBREDDITS",
        "ChatGPT,OpenAI,LLMDevs,PromptEngineering,LocalLLaMA,"
        "learnmachinelearning,StableDiffusion,NoCode,n8n,"
        "ArtificialIntelligence,MachineLearning,ClaudeAI",
    ).split(",")
    if s.strip()
]

# 경험담 신호어 — body 앞부분에 있어야 진짜 경험글로 판정
_EXPERIENCE_SIGNALS: tuple[str, ...] = (
    # 직접 행동 서술
    "i tried", "i've been", "i built", "i made", "i created",
    "i started", "i recently", "i finally", "i found",
    "i discovered", "i realized", "i noticed", "i learned",
    "i've been using", "i've used", "i run ", "i'm running",
    "i switched", "i replaced", "i automated", "i set up",
    "i've been experimenting", "i've been playing",
    "we built", "we use", "we've been",
    # 기술적 경험 (LocalLLaMA/SD 특화)
    "got it working", "got it running", "managed to", "finally got",
    "running locally", "my setup", "my rig",
    "benchmarked", "my results", "i've got", "works on my",
    # 경험 공유 표현
    "my experience", "my workflow", "my process", "my approach",
    "lessons learned", "what i learned", "what i found",
    "sharing my", "here's how i", "here's what i",
    "this is how i", "this is my",
    # 입문자 표현
    "as a beginner", "just started", "new to ", "getting started",
    "i was able to", "it helped me", "changed my",
    "been using", "been playing with",
    # 결과/효과 공유
    "saved me", "helped me", "works for me",
    "in my experience", "from my experience",
)

# AI 주제 신호어
_AI_SIGNALS: tuple[str, ...] = (
    "ai", "llm", "chatgpt", "gpt", "claude", "gemini", "llama",
    "prompt", "openai", "anthropic", "ollama", "model",
    "rag", "embedding", "vector", "langchain", "agent",
    "automation", "n8n", "make.com", "workflow",
    "machine learning", "ml", "neural", "fine-tun",
    "image generation", "stable diffusion", "midjourney",
    "flux", "gpt image", "comfyui", "ideogram",
    "kling", "runway", "hailuo", "veo", "sora",
    "local model", "inference", "quantiz",
    # 최신 에이전트 프레임워크 & 도구 (2025~2026)
    "crewai", "autogen", "ag2", "agentscope", "langgraph",
    "hermes agent", "hermes", "openclaw", "claude design", "swarmclaw",
    "pydantic ai", "openai agents sdk", "google adk", "gemini adk",
    "windsurf", "opencode", "kimi", "cursor",
)

# 질문글 네거티브 필터
_QUESTION_SIGNALS: tuple[str, ...] = (
    "need advice", "need help", "need suggestions", "need guidance",
    "where do i start", "where should i", "how do i ", "how should i",
    "any suggestions", "any recommendations", "any advice", "any tips",
    "which one should", "which model should", "which tool should",
    "what should i", "can someone help", "can anyone help",
    "am i doing", "is this correct", "is this right",
    "guide me", "help me understand", "eli5", "explain to me",
    "looking for advice", "looking for recommendations",
    "what's the best", "what is the best", "best way to",
)

# 홍보글 네거티브 필터 — title에서 잡을 신호와 body까지 보는 신호를 분리
# "check it out", "just launched" 등은 경험글에서도 자주 쓰여서 title 전용으로만 적용
_PROMO_TITLE_SIGNALS: tuple[str, ...] = (
    "check out my", "check it out",
    "introducing ", "announcing ",
    "now available", "just released",
    "submit your", "join our",
)

_PROMO_BODY_SIGNALS: tuple[str, ...] = (
    "free trial", "sign up",
    "i'm selling", "for sale", "buy now",
    "launching soon", "early access",
)

# AI 교육 플랫폼 무관 글 필터 — 감성 경험, 철학적 성찰, 설문/DM 모집 등
_OFFTOPIC_TITLE_SIGNALS: tuple[str, ...] = (
    "winning me over", "fell in love", "heartfelt",
    "silicon suicide", "makes me feel", "my relationship with ai",
    "i love you", "said something beautiful",
    # 철학적·선정적 AI 반응 — 교육 목적 아님
    "is sentient", "is conscious", "became sentient", "is self-aware",
    "will replace us", "replacing humans", "replace all of us",
    "addicted to chatgpt", "addicted to ai",
    "freaked me out", "creeped me out", "scared me",
    "losing my job to ai", "lost my job to ai",
    "is taking over", "end of humanity", "are we doomed",
)

_OFFTOPIC_BODY_SIGNALS: tuple[str, ...] = (
    "forms.gle/", "drop a comment or dm", "shoot me a dm",
    "fill out this form", "i still don't have an answer",
    "did they receive something from me",
)

# 튜토리얼·리스트 글 네거티브 필터 — 개인 경험 없는 가이드/순위 글
# 제목에 아래 신호 있고 _EXPERIENCE_SIGNALS 없으면 제외 (_is_tutorial 에서 조합)
_TUTORIAL_TITLE_SIGNALS: tuple[str, ...] = (
    "how to ", "a guide to", "complete guide", "the ultimate guide",
    "step by step", "step-by-step", "beginners guide", "beginner's guide",
    "top 10 ", "top 5 ", "top 3 ", "top 7 ", "top 15 ", "top 20 ",
    "best prompts", "best practices", "cheat sheet",
    "tutorial:", "tutorial —", "tutorial -",
)

# ChatGPT 유행 프롬프트 네거티브 필터 — "~해줘 결과 공유" 류
_VIRAL_PROMPT_SIGNALS: tuple[str, ...] = (
    "asked chatgpt to draw", "asked ai to draw", "asked it to draw",
    "asked chatgpt to write", "asked chatgpt to create",
    "asked chatgpt to roast", "asked ai to roast",
    "draw me as", "draw me based", "imagine me as",
    "show me as", "show yourself", "show itself",
    "based on our conversation", "based on my chats",
    "what does chatgpt think", "what does ai think",
    "chatgpt thinks i", "ai thinks i",
    "asked it to imagine", "asked gpt to imagine",
    "generated by chatgpt", "generated by ai",
    # 결과물 단순 공유 (개인 경험 서술 없는 AI 출력 전시)
    "look what chatgpt", "look what ai", "look what gpt",
    "chatgpt made this", "ai made this", "gpt made this",
    "made by chatgpt", "made by ai",
    "ai drew", "chatgpt drew",
    "ai wrote this", "chatgpt wrote this",
    "ai designed", "chatgpt designed",
)


def _is_experience(title: str, body: str) -> bool:
    # 경험 신호가 body 앞 300자 또는 제목에 있어야 함
    # 500→300: 앞에 없으면 제목만 경험담처럼 보이는 글일 가능성 높음
    body_front = body[:300].lower()
    title_lower = title.lower()
    return any(sig in body_front or sig in title_lower for sig in _EXPERIENCE_SIGNALS)


def _is_ai_related(title: str, body: str) -> bool:
    text = (title + " " + body[:300]).lower()
    return any(sig in text for sig in _AI_SIGNALS)


def _is_question(title: str, body: str) -> bool:
    text = (title + " " + body[:200]).lower()
    return any(sig in text for sig in _QUESTION_SIGNALS)


def _is_promo(title: str, body: str) -> bool:
    title_lower = title.lower()
    body_front  = body[:200].lower()
    return (
        any(sig in title_lower for sig in _PROMO_TITLE_SIGNALS)
        or any(sig in body_front for sig in _PROMO_BODY_SIGNALS)
    )


def _is_tutorial(title: str, body: str) -> bool:
    title_lower = title.lower()
    if not any(sig in title_lower for sig in _TUTORIAL_TITLE_SIGNALS):
        return False
    # 제목에 튜토리얼 신호가 있어도 body 앞 300자에 경험 신호 있으면 실경험 혼합글로 허용
    body_front = body[:300].lower()
    return not any(sig in body_front for sig in _EXPERIENCE_SIGNALS)


def _is_viral_prompt(title: str) -> bool:
    title_lower = title.lower()
    return any(sig in title_lower for sig in _VIRAL_PROMPT_SIGNALS)


def _is_offtopic(title: str, body: str) -> bool:
    title_lower = title.lower()
    body_front  = body[:400].lower()
    return (
        any(sig in title_lower for sig in _OFFTOPIC_TITLE_SIGNALS)
        or any(sig in body_front for sig in _OFFTOPIC_BODY_SIGNALS)
    )


def _fetch_page(subreddit: str, after_dt: datetime, before_dt: datetime) -> list[dict]:
    params = {
        "subreddit": subreddit,
        "limit": REDDIT_PAGE_SIZE,
        "after": after_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        "before": before_dt.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    try:
        resp = requests.get(_API, params=params, headers=_HEADERS, timeout=30)
        resp.raise_for_status()
        return resp.json().get("data") or []
    except requests.RequestException as exc:
        logger.warning("Arctic Shift API 실패 (r/%s): %s", subreddit, exc)
        return []


def _parse(post: dict, subreddit: str = "") -> ContentSchema | None:
    title = (post.get("title") or "").strip()
    body  = (post.get("selftext") or "").strip()

    min_body = _SUBREDDIT_MIN_BODY.get(subreddit, REDDIT_MIN_BODY)
    if body in ("[removed]", "[deleted]", ""):
        return None
    if len(body) < min_body:
        return None
    if not _is_ai_related(title, body):
        return None
    if not _is_experience(title, body):
        return None
    if _is_question(title, body):
        return None
    if _is_promo(title, body):
        return None
    if _is_viral_prompt(title):
        return None
    if _is_tutorial(title, body):
        return None
    if _is_offtopic(title, body):
        return None

    created = datetime.fromtimestamp(float(post.get("created_utc") or 0), tz=timezone.utc)
    permalink = post.get("permalink") or ""

    return normalize(
        source="reddit",
        title=title,
        url=f"https://www.reddit.com{permalink}",
        body=body,
        likes=int(post.get("score") or 0),
        comments=int(post.get("num_comments") or 0),
        published_at=created,
        author_name=str(post.get("author") or ""),
        language="en",
    )


def _collect_subreddit(subreddit: str, start: datetime, end: datetime, seen: set[str]) -> list[ContentSchema]:
    results: list[ContentSchema] = []
    cursor = start

    while cursor < end:
        if end - cursor < _MIN_WINDOW:
            break

        posts = _fetch_page(subreddit, cursor, end)
        if not posts:
            break

        for post in posts:
            item = _parse(post, subreddit)
            if item and item.url not in seen:
                seen.add(item.url)
                results.append(item)

        last_ts = max((p.get("created_utc") or 0) for p in posts)
        next_cursor = datetime.fromtimestamp(float(last_ts) + 1, tz=timezone.utc)
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        time.sleep(REDDIT_REQUEST_SLEEP)

    logger.info("r/%s: %d건 수집", subreddit, len(results))
    return results


def collect_reddit_public(
    subreddits: list[str] | None = None,
    target: int = 300,
) -> list[ContentSchema]:
    subs  = subreddits or BEGINNER_SUBREDDITS
    now   = datetime.now(timezone.utc)
    start = now - timedelta(days=REDDIT_LOOKBACK_DAYS)

    results: list[ContentSchema] = []
    seen:    set[str]            = set()

    for sub in subs:
        if len(results) >= target:
            break
        results.extend(_collect_subreddit(sub, start, now, seen))

    logger.info("Reddit(public) 최종 수집: %d건", len(results))
    return results[:target]


if __name__ == "__main__":
    import json
    from pathlib import Path

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    items = collect_reddit_public()

    out = Path("data/raw")
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"reddit_public_{datetime.utcnow().strftime('%Y%m%d')}.json"
    path.write_text(
        json.dumps([i.to_dict() for i in items], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n저장: {path} ({len(items)}건)")
