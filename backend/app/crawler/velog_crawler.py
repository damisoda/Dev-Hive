from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import requests

from app.crawler.normalizer import ContentSchema, clean_body, normalize

logger = logging.getLogger(__name__)

VELOG_GQL_URL = "https://v2.velog.io/graphql"
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT_SECONDS", "30"))
VELOG_TARGET_ITEMS = int(os.getenv("VELOG_TARGET_ITEMS", "300"))
VELOG_PAGE_SIZE = int(os.getenv("VELOG_PAGE_SIZE", "20"))
VELOG_MAX_PAGES_PER_KEYWORD = int(os.getenv("VELOG_MAX_PAGES_PER_KEYWORD", "5"))
VELOG_REQUEST_SLEEP = float(os.getenv("VELOG_REQUEST_SLEEP", "0.5"))
VELOG_MIN_LIKES = int(os.getenv("VELOG_MIN_LIKES", "0"))
VELOG_FETCH_FULL_BODY = os.getenv("VELOG_FETCH_FULL_BODY", "true").lower() != "false"
VELOG_MIN_BODY_LEN = int(os.getenv("VELOG_MIN_BODY_LEN", "500"))

# haiku_tagging_prompt.md 의 7개 대주제를 커버하는 검색 키워드
# 대주제: 프롬프트엔지니어링 / Agentic AI / 멀티모달 AI /
#          RAG & 지식관리 / 오픈소스 AI / AI 워크플로우 & 자동화 / AI 엔지니어링
VELOG_SEARCH_KEYWORDS: list[str] = [
    kw.strip()
    for kw in os.getenv(
        "VELOG_SEARCH_KEYWORDS",
        # 프롬프트 엔지니어링
        "프롬프트,프롬프트엔지니어링,"
        # Agentic AI
        "에이전트,MCP,멀티에이전트,claude code,"
        # 멀티모달 AI
        "이미지생성,멀티모달,"
        # RAG & 지식 관리
        "RAG,langchain,임베딩,"
        # 오픈소스 AI
        "LLM,ollama,파인튜닝,huggingface,"
        # AI 워크플로우 & 자동화
        "n8n,자동화,make.com,"
        # AI 엔지니어링
        "MLOps,LLMOps,AI개발,"
        # 경험/후기 (입문·중급 경험담 확보용)
        "AI 후기,LLM 후기,ChatGPT 후기,AI 사용 후기,"
        "개발 회고,AI 회고,프로젝트 후기,"
        "AI 입문,LLM 입문,AI 공부,AI 독학",
    ).split(",")
    if kw.strip()
]

# 비공식 GraphQL API (https://v2.velog.io/graphql) 기반.
# 인트로스펙션 비활성화 상태라 스키마는 탐색으로 확인함.
# searchPosts: 플랫폼 전체 키워드 검색 (offset 페이지네이션)
# posts(username, cursor): 유저별 게시글 (커서 페이지네이션, cursor = 마지막 post.id)

_SEARCH_POSTS_QUERY = """
query SearchPosts($keyword: String!, $limit: Int!, $offset: Int!) {
  searchPosts(keyword: $keyword, limit: $limit, offset: $offset) {
    count
    posts {
      id
      title
      short_description
      url_slug
      user { username }
      tags
      released_at
      likes
      comments_count
    }
  }
}
"""

_USER_POSTS_QUERY = """
query UserPosts($username: String!, $cursor: ID) {
  posts(username: $username, cursor: $cursor) {
    id
    title
    short_description
    url_slug
    tags
    released_at
    likes
    comments_count
  }
}
"""

_POST_BODY_QUERY = """
query ReadPost($username: String!, $url_slug: String!) {
  post(username: $username, url_slug: $url_slug) {
    body
  }
}
"""

# 7개 대주제(haiku_tagging_prompt.md) 기반 태그 허용 목록
# 이 중 하나라도 포함된 게시글만 수집 — 도메인 무관 글 필터링
_AI_TAGS: frozenset[str] = frozenset(
    tag.casefold()
    for tag in [
        # 공통 / 범용
        "AI", "인공지능", "LLM", "ChatGPT", "GPT", "GPT-4", "GPT-3",
        "claude", "gemini", "openai", "anthropic",
        # 프롬프트 엔지니어링
        "프롬프트", "프롬프트엔지니어링", "prompt", "few-shot", "cot",
        "chain of thought", "시스템프롬프트",
        # Agentic AI
        "에이전트", "agent", "agentic", "MCP", "멀티에이전트", "multi-agent",
        "claude code", "codex", "langgraph", "crewai", "autogen",
        "도구호출", "tool use", "function calling",
        # 멀티모달 AI
        "멀티모달", "multimodal", "이미지생성", "image generation",
        "VLM", "비전모델", "sora", "midjourney", "stable diffusion",
        "diffusion", "text-to-image", "텍스트투이미지",
        # RAG & 지식 관리
        "RAG", "임베딩", "embedding", "벡터DB", "vector db", "벡터데이터베이스",
        "langchain", "llamaindex", "검색증강생성", "pinecone", "pgvector",
        "obsidian", "지식관리", "knowledge base",
        # 오픈소스 AI
        "huggingface", "ollama", "vllm", "파인튜닝", "fine-tuning", "lora",
        "로컬AI", "로컬LLM", "오픈소스AI", "transformer", "머신러닝", "딥러닝",
        "자연어처리", "nlp", "ml",
        # AI 워크플로우 & 자동화
        "n8n", "make.com", "zapier", "자동화", "업무자동화", "AI자동화",
        "workflow", "워크플로우", "반복작업자동화",
        # AI 엔지니어링
        "MLOps", "LLMOps", "AI개발", "AI엔지니어링", "배포", "fastapi",
        "풀스택AI", "성능최적화", "프로덕션AI", "copilot",
    ]
)

# AI/ML 글을 작성하는 시드 유저 목록
# 팀에서 직접 확인한 양질의 작성자를 여기에 추가하세요 (velog.io/@<username>)
VELOG_SEED_USERS: list[str] = [
    # velog_seed_finder --experience-first (pages=5) 결과
    # 조건: AI 도메인 키워드 검색에서 발견 + 경험글 비율 높음 + 수집 검증 완료
    "teo",           # 9021좋아요, 29글, 31%경험, 4도메인
    "ken708",        # 3240좋아요, 20글, 50%경험, Agentic·오픈소스·멀티모달
    "addiescode",    # 3564좋아요, 9글,  100%경험, AI엔지니어링
    "hayounsong",    # 3204좋아요, 9글,  100%경험, AI엔지니어링
    "velopert",      # 3168좋아요, 20글, 80%경험, AI엔지니어링
    "ansrjsdn",      # 1671좋아요, 14글, 86%경험, AI엔지니어링
    "kim-taewoo",    # 1689좋아요, 9글,  100%경험, AI엔지니어링
    "bokdol11859",   # 1116좋아요, 9글,  100%경험, 멀티모달AI
    "hmmhmmhm",      # 807좋아요,  3글,  100%경험, 멀티모달AI·프롬프트
    "hustle-dev",    # 611좋아요,  1글,  100%경험, AI엔지니어링
    "k-svelte-master",  # 481좋아요, 4글, 25%경험, Agentic·프롬프트
    "jujini31",      # 43좋아요,   1글,  100%경험, Agentic AI (Codex·MCP)
]


def _gql(query: str, variables: dict[str, Any]) -> dict[str, Any] | None:
    try:
        resp = requests.post(
            VELOG_GQL_URL,
            json={"query": query, "variables": variables},
            timeout=HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        logger.warning("Velog GQL 요청 실패: %s", exc)
        return None


def _parse_dt(date_str: str | None) -> datetime:
    if not date_str:
        return datetime.utcnow()
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except ValueError:
        return datetime.utcnow()


def _is_ai_related(tags: list[str]) -> bool:
    return any(tag.casefold() in _AI_TAGS for tag in tags)


def _make_url(username: str, url_slug: str) -> str:
    return f"https://velog.io/@{username}/{url_slug}"


def _fetch_body(username: str, url_slug: str) -> str:
    data = _gql(_POST_BODY_QUERY, {"username": username, "url_slug": url_slug})
    if not data:
        return ""
    raw = ((data.get("data") or {}).get("post") or {}).get("body") or ""
    return clean_body(raw)


def _to_content(post: dict[str, Any], username: str) -> ContentSchema | None:
    url_slug = post.get("url_slug") or ""
    if VELOG_FETCH_FULL_BODY and url_slug:
        body = _fetch_body(username, url_slug)
        time.sleep(VELOG_REQUEST_SLEEP)
    else:
        body = post.get("short_description") or ""

    if len(body) < VELOG_MIN_BODY_LEN:
        logger.debug("body 짧아 제외 (%d자): @%s/%s", len(body), username, url_slug)
        return None

    return normalize(
        title=post.get("title") or "",
        source="velog",
        url=_make_url(username, url_slug),
        published_at=_parse_dt(post.get("released_at")),
        body=body,
        author_name=username,
        language="ko",
        likes=int(post.get("likes") or 0),
        comments=int(post.get("comments_count") or 0),
    )


def fetch_by_keyword(keyword: str, seen_urls: set[str]) -> list[ContentSchema]:
    results: list[ContentSchema] = []

    for page in range(VELOG_MAX_PAGES_PER_KEYWORD):
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

            if int(post.get("likes") or 0) < VELOG_MIN_LIKES:
                continue

            seen_urls.add(url)
            item = _to_content(post, username)
            if item is not None:
                results.append(item)

        time.sleep(VELOG_REQUEST_SLEEP)

    logger.info("키워드 '%s': %d건 수집", keyword, len(results))
    return results


def fetch_by_user(username: str, seen_urls: set[str]) -> list[ContentSchema]:
    results: list[ContentSchema] = []
    cursor: str | None = None

    while True:
        variables: dict[str, Any] = {"username": username}
        if cursor:
            variables["cursor"] = cursor

        data = _gql(_USER_POSTS_QUERY, variables)
        if not data:
            break

        posts: list[dict] = ((data.get("data") or {}).get("posts")) or []
        if not posts:
            break

        for post in posts:
            url_slug = post.get("url_slug") or ""
            if not url_slug:
                continue

            url = _make_url(username, url_slug)
            if url in seen_urls:
                continue

            # 시드 유저는 AI 작성자로 사전 검증됐으므로 태그 필터 미적용
            if int(post.get("likes") or 0) < VELOG_MIN_LIKES:
                continue

            seen_urls.add(url)
            item = _to_content(post, username)
            if item is not None:
                results.append(item)

        # 마지막 post.id가 다음 페이지 커서
        cursor = posts[-1].get("id")
        time.sleep(VELOG_REQUEST_SLEEP)

        if len(posts) < VELOG_PAGE_SIZE:
            break

    logger.info("유저 '%s': %d건 수집", username, len(results))
    return results


def _load_seen_urls(data_dir: Path = Path("data/raw")) -> set[str]:
    """기존 수집 파일에서 URL을 로드해 재수집 시 중복을 방지한다."""
    seen: set[str] = set()
    for f in data_dir.glob("velog_*.json"):
        try:
            items = json.loads(f.read_text(encoding="utf-8"))
            seen.update(
                item["url"] for item in items
                if isinstance(item, dict) and item.get("url")
            )
        except Exception:
            pass
    return seen


def collect_velog(target: int = VELOG_TARGET_ITEMS, skip_seen: bool = True) -> list[ContentSchema]:
    seen_urls: set[str] = _load_seen_urls() if skip_seen else set()
    if seen_urls:
        logger.info("기존 수집 URL %d건 로드 — 중복 제외", len(seen_urls))
    results: list[ContentSchema] = []

    for keyword in VELOG_SEARCH_KEYWORDS:
        if len(results) >= target:
            break
        results.extend(fetch_by_keyword(keyword, seen_urls))

    for username in VELOG_SEED_USERS:
        if len(results) >= target:
            break
        results.extend(fetch_by_user(username, seen_urls))

    logger.info("Velog 최종 수집: %d건", len(results))
    return results[:target]


def save_json(items: list[ContentSchema], path: Optional[str] = None) -> str:
    if path is None:
        out_dir = Path("data/raw")
        out_dir.mkdir(parents=True, exist_ok=True)
        date_str = datetime.utcnow().strftime("%Y%m%d")
        path = str(out_dir / f"velog_{date_str}.json")

    with open(path, "w", encoding="utf-8") as f:
        json.dump([item.to_dict() for item in items], f, ensure_ascii=False, indent=2)

    logger.info("저장 완료: %s (%d건)", path, len(items))
    return path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    items = collect_velog()
    save_json(items)
