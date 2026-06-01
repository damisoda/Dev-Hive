import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from langdetect import detect, LangDetectException

from app.crawler.normalizer import ContentSchema, normalize

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

ALGOLIA_URL = "https://hn.algolia.com/api/v1/search"

TOPIC_QUERIES: dict[str, list[str]] = {
    "prompt_engineering": ["prompt engineering", "chain of thought", "few-shot", "system prompt"],
    "agentic_ai":         ["AI agent", "MCP protocol", "LangGraph", "multi-agent", "autonomous AI"],
    "multimodal":         ["multimodal AI", "image generation AI", "vision model", "Stable Diffusion"],
    "rag":                ["RAG retrieval", "vector database", "text embedding", "retrieval augmented"],
    "open_source_ai":     ["Ollama", "open source LLM", "fine-tuning LLM", "LoRA", "HuggingFace"],
    "ai_workflow":        ["AI automation", "n8n AI", "Cursor IDE", "Claude Code", "AI workflow"],
    "ai_engineering":     ["AI engineering", "LLM API", "MLOps"],
}

MIN_POINTS = 10
MIN_COMMENTS = 5


def _parse_dt(date_str: Optional[str]) -> datetime:
    if not date_str:
        return datetime.utcnow()
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except ValueError:
        return datetime.utcnow()


def _pass_rule_filter(title: str, body: Optional[str]) -> bool:
    if title.strip().endswith("?") and (not body or len(body) < 50):
        return False
    if body and body.startswith("http") and "\n" not in body:
        return False
    text = body or title
    try:
        if detect(text) not in ("en", "ko"):
            return False
    except LangDetectException:
        return False
    return True


def fetch_stories(query: str, limit: int = 100) -> list[ContentSchema]:
    try:
        res = requests.get(
            ALGOLIA_URL,
            params={
                "query": query,
                "tags": "story",
                "hitsPerPage": limit,
                "numericFilters": [f"points>={MIN_POINTS}", f"num_comments>={MIN_COMMENTS}"],
            },
            timeout=10,
        )
        res.raise_for_status()
    except requests.RequestException as e:
        log.warning("stories fetch failed: %s", e)
        return []

    items = []
    for hit in res.json().get("hits", []):
        title = hit.get("title") or ""
        body = hit.get("story_text") or ""
        if not title:
            continue
        if not _pass_rule_filter(title, body):
            continue
        items.append(normalize(
            title=title,
            source="hn",
            url=hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
            published_at=_parse_dt(hit.get("created_at")),
            body=body,
            author_name=hit.get("author"),
            likes=hit.get("points", 0),
            comments=hit.get("num_comments", 0),
        ))
    return items


def fetch_comments(query: str, limit: int = 50) -> list[ContentSchema]:
    try:
        res = requests.get(
            ALGOLIA_URL,
            params={
                "query": query,
                "tags": "comment",
                "hitsPerPage": limit,
            },
            timeout=10,
        )
        res.raise_for_status()
    except requests.RequestException as e:
        log.warning("comments fetch failed: %s", e)
        return []

    items = []
    for hit in res.json().get("hits", []):
        body = hit.get("comment_text") or ""
        if len(body) < 50:
            continue
        try:
            if detect(body) not in ("en", "ko"):
                continue
        except LangDetectException:
            continue
        items.append(normalize(
            title=f"[HN comment] {hit.get('story_title') or 'unknown'}",
            source="hn",
            url=f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
            published_at=_parse_dt(hit.get("created_at")),
            body=body,
            author_name=hit.get("author"),
        ))
    return items


def crawl_all(story_limit: int = 100, comment_limit: int = 50) -> list[ContentSchema]:
    seen_urls: set[str] = set()
    results: list[ContentSchema] = []

    for topic, queries in TOPIC_QUERIES.items():
        topic_stories, topic_comments = 0, 0
        for query in queries:
            for item in fetch_stories(query, story_limit) + fetch_comments(query, comment_limit):
                if item.url in seen_urls:
                    continue
                seen_urls.add(item.url)
                results.append(item)
                if item.title.startswith("[HN comment]"):
                    topic_comments += 1
                else:
                    topic_stories += 1
        log.info("[%s] stories=%d  comments=%d", topic, topic_stories, topic_comments)

    log.info("총 수집(중복 제거): %d건", len(results))
    return results


def save_json(items: list[ContentSchema], path: Optional[str] = None) -> str:
    if path is None:
        out_dir = Path("data/raw")
        out_dir.mkdir(parents=True, exist_ok=True)
        date_str = datetime.utcnow().strftime("%Y%m%d")
        path = str(out_dir / f"hackernews_{date_str}.json")

    with open(path, "w", encoding="utf-8") as f:
        json.dump([item.to_dict() for item in items], f, ensure_ascii=False, indent=2)

    log.info("저장 완료: %s (%d건)", path, len(items))
    return path


if __name__ == "__main__":
    items = crawl_all()
    save_json(items)
