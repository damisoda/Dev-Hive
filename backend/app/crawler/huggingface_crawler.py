import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests

from app.crawler.normalizer import ContentSchema, normalize

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

HF_API_URL = "https://huggingface.co/api/daily_papers"


def _parse_dt(date_str: Optional[str]) -> datetime:
    if not date_str:
        return datetime.utcnow()
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except ValueError:
        return datetime.utcnow()


def fetch_daily_papers(date: str) -> list[ContentSchema]:
    try:
        res = requests.get(HF_API_URL, params={"date": date}, timeout=10)
        res.raise_for_status()
    except requests.RequestException as e:
        log.warning("fetch failed [%s]: %s", date, e)
        return []

    items = []
    for entry in res.json():
        paper = entry.get("paper", {})
        upvotes = paper.get("upvotes", 0)
        authors = paper.get("authors", [])
        author_name = authors[0].get("name") if authors else None

        items.append(normalize(
            title=paper.get("title") or entry.get("title") or "",
            source="huggingface",
            url=f"https://huggingface.co/papers/{paper.get('id', '')}",
            published_at=_parse_dt(paper.get("publishedAt")),
            body=paper.get("summary") or entry.get("summary") or "",
            author_name=author_name,
            likes=upvotes,
            comments=entry.get("numComments", 0),
        ))
    return items


def crawl_all(days: int = 7) -> list[ContentSchema]:
    seen_urls: set[str] = set()
    results: list[ContentSchema] = []

    today = datetime.utcnow().date()
    for i in range(days):
        date = (today - timedelta(days=i)).isoformat()
        papers = fetch_daily_papers(date)
        log.info("[%s] %d건", date, len(papers))
        for item in papers:
            if item.url in seen_urls:
                continue
            seen_urls.add(item.url)
            results.append(item)

    log.info("총 수집(중복 제거): %d건", len(results))
    return results


def save_json(items: list[ContentSchema], path: Optional[str] = None) -> str:
    if path is None:
        out_dir = Path("data/raw")
        out_dir.mkdir(parents=True, exist_ok=True)
        date_str = datetime.utcnow().strftime("%Y%m%d")
        path = str(out_dir / f"huggingface_{date_str}.json")

    with open(path, "w", encoding="utf-8") as f:
        json.dump([item.to_dict() for item in items], f, ensure_ascii=False, indent=2)

    log.info("저장 완료: %s (%d건)", path, len(items))
    return path


if __name__ == "__main__":
    items = crawl_all(days=7)
    save_json(items)
