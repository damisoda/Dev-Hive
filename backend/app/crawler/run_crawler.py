from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from app.crawler.github_crawler import collect_github
from app.crawler.google_drive_uploader import upload_to_drive
from app.crawler.reddit_crawler import DEFAULT_SUBREDDITS, collect_reddit
from app.crawler.velog_crawler import collect_velog

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
RAW_DATA_DIR = BACKEND_ROOT / "data" / "raw"


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


def load_existing_urls(raw_dir: str | Path = RAW_DATA_DIR) -> set[str]:
    raw_path = Path(raw_dir)
    urls: set[str] = set()
    if not raw_path.exists():
        return urls

    for json_path in raw_path.glob("*.json"):
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Failed to read existing raw file: %s", json_path)
            continue
        if not isinstance(payload, list):
            continue
        for item in payload:
            if isinstance(item, dict) and item.get("url"):
                urls.add(str(item["url"]))

    logger.info("Loaded %s existing URLs from %s", len(urls), raw_path)
    return urls


def filter_existing_urls(items: list[Any], existing_urls: set[str]) -> list[Any]:
    filtered: list[Any] = []
    for item in items:
        url = _item_url(item)
        if not url or url in existing_urls:
            continue
        filtered.append(item)
    return filtered


def _dedupe_dicts_by_url(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        url = str(item.get("url") or "")
        if not url or url in seen:
            continue
        seen.add(url)
        deduped.append(item)
    return deduped


def save_json(items: list[Any], output_dir: str | Path = RAW_DATA_DIR) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime("%Y%m%d")
    file_path = output_path / f"_{today}.json"

    previous_payload: list[dict[str, Any]] = []
    if file_path.exists():
        try:
            loaded = json.loads(file_path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                previous_payload = [item for item in loaded if isinstance(item, dict)]
        except Exception:
            logger.exception("Failed to load today's raw file before merge: %s", file_path)

    payload = _dedupe_dicts_by_url(previous_payload + [_schema_to_dict(item) for item in items])
    temp_path = file_path.with_suffix(".json.tmp")

    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(file_path)

    logger.info("Saved %s items to %s", len(payload), file_path)
    return file_path


def crawl_github() -> list[Any]:
    items = collect_github(300)
    deduped = dedupe_by_url(items)

    logger.info(
        "GitHub crawl finished. github=%s deduped=%s",
        len(items),
        len(deduped),
    )
    return deduped


def crawl_reddit() -> list[Any]:
    items = collect_reddit(DEFAULT_SUBREDDITS, 600)
    deduped = dedupe_by_url(items)

    logger.info(
        "Reddit crawl finished. reddit=%s deduped=%s",
        len(items),
        len(deduped),
    )
    return deduped


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


def run_pipeline(crawl_func=crawl_all) -> Path | None:
    existing_urls = load_existing_urls()
    items = crawl_func()
    new_items = filter_existing_urls(items, existing_urls)
    new_items = dedupe_by_url(new_items)

    logger.info(
        "Filtered against existing raw data. crawled=%s new=%s",
        len(items),
        len(new_items),
    )
    if not new_items:
        logger.info("No new crawl items to save or upload")
        return None

    saved_path = save_json(new_items)
    try:
        upload_to_drive(saved_path)
    except Exception:
        logger.exception("Google Drive upload failed after crawl: %s", saved_path)
    return saved_path


def main() -> None:
    run_pipeline(crawl_all)


if __name__ == "__main__":
    main()
# 팀 아키텍처 규칙 반영 완료 - 규원
