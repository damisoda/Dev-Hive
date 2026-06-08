from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

from app.crawler.github_crawler import collect_github
from app.crawler.reddit_crawler import DEFAULT_SUBREDDITS, collect_reddit
from app.crawler.velog_crawler import collect_velog

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


def _schema_to_dict(item: Any) -> dict[str, Any]:
    if hasattr(item, "model_dump"):
        return item.model_dump(mode="json")
    if hasattr(item, "dict"):
        return item.dict()
    if hasattr(item, "__dict__"):
        return dict(item.__dict__)
    raise TypeError(f"Unsupported schema object: {type(item)!r}")


def _item_url(item: Any) -> str:
    if hasattr(item, "url"):
        return str(item.url)
    if isinstance(item, dict):
        return str(item.get("url") or "")
    return ""


def dedupe_by_url(items: list[Any]) -> list[Any]:
    deduped = []
    seen_urls = set()

    for item in items:
        url = _item_url(item)
        if not url or url in seen_urls:
            continue

        seen_urls.add(url)
        deduped.append(item)

    return deduped


def save_json(items: list[Any], output_dir: str | Path = "data/raw") -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime("%Y%m%d")
    file_path = output_path / f"_{today}.json"

    payload = [_schema_to_dict(item) for item in items]
    temp_path = file_path.with_suffix(".json.tmp")

    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(file_path)

    logger.info("Saved %s items to %s", len(payload), file_path)
    return file_path


def crawl_all() -> list[Any]:
    with ThreadPoolExecutor(max_workers=3) as executor:
        reddit_future = executor.submit(collect_reddit, DEFAULT_SUBREDDITS, 600)
        github_future = executor.submit(collect_github, 300)
        velog_future = executor.submit(collect_velog, 300)

        reddit_items = reddit_future.result()
        github_items = github_future.result()
        velog_items = velog_future.result()

    merged = reddit_items + github_items + velog_items
    deduped = dedupe_by_url(merged)

    logger.info(
        "Crawl finished. reddit=%s github=%s velog=%s merged=%s deduped=%s",
        len(reddit_items),
        len(github_items),
        len(velog_items),
        len(merged),
        len(deduped),
    )

    return deduped


def main() -> None:
    items = crawl_all()
    save_json(items)


if __name__ == "__main__":
    main()
# 팀 아키텍처 규칙 반영 완료 
