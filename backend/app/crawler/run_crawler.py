from __future__ import annotations

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from dotenv import load_dotenv

load_dotenv()

from app.crawler.github_crawler import collect_github
from app.crawler.github_discussions_crawler import collect_github_discussions
from app.crawler.google_drive_uploader import upload_to_drive
from app.crawler.huggingface_crawler import crawl_all as _collect_huggingface
from app.crawler.reddit_crawler import DEFAULT_SUBREDDITS, collect_reddit
from app.crawler.reddit_public_crawler import collect_reddit_public
from app.crawler.velog_beginner_crawler import collect_velog_beginner
from app.crawler.velog_crawler import collect_velog
from app.crawler.x_crawler import collect_x_seed_users

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
RAW_DATA_DIR = BACKEND_ROOT / "data" / "raw"


def _schema_to_dict(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return item
    if hasattr(item, "model_dump"):
        return item.model_dump(mode="json")
    if hasattr(item, "dict"):
        return item.dict()
    if hasattr(item, "__dict__"):
        return dict(item.__dict__)
    raise TypeError(f"Unsupported schema object: {type(item)!r}")


def _normalize_url(url: str) -> str:
    """dedup 비교용 URL 정규화: 스킴/호스트 소문자, 끝 슬래시·fragment 제거(쿼리는 보존).

    트레일링 슬래시/대소문자/fragment 변형으로 같은 글이 재태깅·재임베딩되는 비용 누수를 막는다.
    파싱 실패 시 strip만 한 원본을 반환(절대 깨지지 않음).
    """
    u = (url or "").strip()
    if not u:
        return ""
    try:
        p = urlsplit(u)
        return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), p.query, ""))
    except Exception:
        return u


def _item_url(item: Any) -> str:
    if hasattr(item, "url"):
        return _normalize_url(str(item.url))
    if isinstance(item, dict):
        return _normalize_url(str(item.get("url") or ""))
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
                urls.add(_normalize_url(str(item["url"])))

    logger.info("Loaded %s existing URLs from %s", len(urls), raw_path)
    return urls


def load_existing_urls_from_db(engine_or_url: Any = None) -> set[str]:
    """content 테이블에 이미 적재된 url 집합을 반환한다.

    크롤 직후·적재 전 단계에서 이 집합으로 거르면, 이미 DB에 들어간 항목을 다시 저장/업로드/
    재태깅하지 않는다(비싼 LLM 단계 전에 비용 절감).

    절대 크롤을 깨지 않는다(precision/robustness 우선):
        DATABASE_URL이 없거나, 엔진 생성·쿼리가 실패하면 **빈 집합**을 반환하고 로깅만 한다.

    Args:
        engine_or_url: SQLAlchemy Engine 또는 DB URL 문자열. None이면 DATABASE_URL 환경변수 사용.
    """
    from sqlalchemy import text
    from sqlalchemy.engine import Engine

    urls: set[str] = set()
    engine = None
    created_locally = False
    try:
        if isinstance(engine_or_url, Engine):
            engine = engine_or_url
        else:
            db_url = engine_or_url or os.getenv("DATABASE_URL")
            if not db_url:
                logger.info("DATABASE_URL 없음 — DB 기반 dedup 생략(빈 집합)")
                return urls
            from sqlalchemy import create_engine

            engine = create_engine(db_url)
            created_locally = True

        with engine.connect() as conn:
            rows = conn.execute(text("SELECT url FROM content WHERE url IS NOT NULL")).fetchall()
        for row in rows:
            url = row[0]
            if url:
                urls.add(_normalize_url(str(url)))
        logger.info("Loaded %s existing URLs from DB", len(urls))
    except Exception:
        logger.exception("DB 기반 dedup 조회 실패 — 빈 집합으로 진행(크롤 유지)")
        return set()
    finally:
        # 로컬에서 만든 엔진만 정리한다(주입받은 엔진은 호출자 소유 — 데몬 풀 누수 방지).
        if created_locally and engine is not None:
            engine.dispose()

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


def crawl_velog() -> list[Any]:
    items = collect_velog(300)
    deduped = dedupe_by_url(items)

    logger.info(
        "Velog crawl finished. velog=%s deduped=%s",
        len(items),
        len(deduped),
    )
    return deduped


def crawl_github_discussions() -> list[Any]:
    try:
        items = collect_github_discussions()
        deduped = dedupe_by_url(items)
        logger.info("GitHub Discussions crawl finished. items=%s deduped=%s", len(items), len(deduped))
        return deduped
    except Exception:
        logger.warning("GitHub Discussions crawl skipped (GITHUB_TOKEN 없음 또는 오류)", exc_info=True)
        return []


def crawl_x() -> list[Any]:
    try:
        items = collect_x_seed_users()
        deduped = dedupe_by_url(items)
        logger.info("X crawl finished. items=%s deduped=%s", len(items), len(deduped))
        return deduped
    except Exception:
        logger.error("X crawl skipped (APIFY_TOKEN 없음 또는 오류)", exc_info=True)
        return []


def crawl_velog_beginner() -> list[Any]:
    items = collect_velog_beginner()
    deduped = dedupe_by_url(items)
    logger.info("Velog Beginner crawl finished. items=%s deduped=%s", len(items), len(deduped))
    return deduped


def crawl_reddit_public() -> list[Any]:
    items = collect_reddit_public()
    deduped = dedupe_by_url(items)
    logger.info("Reddit(public) crawl finished. items=%s deduped=%s", len(items), len(deduped))
    return deduped


def crawl_huggingface() -> list[Any]:
    items = _collect_huggingface(days=7)
    deduped = dedupe_by_url(items)
    logger.info("HuggingFace crawl finished. items=%s deduped=%s", len(items), len(deduped))
    return deduped


def crawl_all() -> list[Any]:
    _CRAWLERS = {
        "reddit": lambda: collect_reddit(DEFAULT_SUBREDDITS, 600),
        "reddit_public": crawl_reddit_public,
        "github": lambda: collect_github(300),
        "velog": lambda: collect_velog(300),
        "github_discussions": crawl_github_discussions,
        "x": crawl_x,
        "velog_beginner": crawl_velog_beginner,
        "huggingface": crawl_huggingface,
    }
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {name: executor.submit(fn) for name, fn in _CRAWLERS.items()}

    results: dict[str, list[Any]] = {}
    for name, future in futures.items():
        try:
            results[name] = future.result()
        except Exception:
            logger.exception("크롤 실패: %s", name)
            results[name] = []

    merged = [item for items in results.values() for item in items]
    deduped = dedupe_by_url(merged)

    logger.info(
        "Crawl finished. %s merged=%s deduped=%s",
        " ".join(f"{k}={len(v)}" for k, v in results.items()),
        len(merged),
        len(deduped),
    )
    return deduped


def _is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def _maybe_ingest(new_items: list[Any]) -> None:
    """크롤 직후 적재(QC→태깅→임베딩→DB). 키가 없거나 실패해도 크롤을 절대 깨지 않는다.

    조건:
        - ANTHROPIC_API_KEY / OPENAI_API_KEY / DATABASE_URL 모두 존재
        - INGEST_AFTER_CRAWL이 truthy (미설정=ON 기본값)
    하나라도 빠지면 로깅 후 스킵(크롤+저장+업로드 동작은 그대로 유지).
    """
    ingest_flag = os.getenv("INGEST_AFTER_CRAWL")
    if ingest_flag is not None and not _is_truthy(ingest_flag):
        logger.info("INGEST_AFTER_CRAWL=off — 적재 스킵")
        return

    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    db_url = os.getenv("DATABASE_URL")
    if not (anthropic_key and openai_key and db_url):
        logger.info("API 키/DB URL 부재 — 적재 스킵(크롤+저장+업로드만 수행)")
        return

    engine = None
    try:
        import anthropic
        from openai import OpenAI
        from sqlalchemy import create_engine

        from app.tagging.ingest import ingest_items

        payload = [_schema_to_dict(item) for item in new_items]
        anthropic_client = anthropic.Anthropic(api_key=anthropic_key)
        openai_client = OpenAI(api_key=openai_key)
        engine = create_engine(db_url)

        stats = ingest_items(payload, anthropic_client, openai_client, engine)
        logger.info("크롤 후 적재 완료: %s", json.dumps(stats.get("qc_report", {}), ensure_ascii=False))
        logger.info(
            "적재 통계 — 적재:%s / quality:%s / 중복:%s / 태깅실패:%s / 적재오류:%s",
            stats["inserted"], stats["skipped_quality"], stats["skipped_dup"],
            stats["tag_failed"], stats["load_failed"],
        )
    except Exception:
        # 적재 실패가 스케줄 크롤을 절대 죽이지 않는다.
        logger.exception("크롤 후 적재 실패 — 크롤/저장/업로드는 유지")
    finally:
        # 데몬에서 매 크롤마다 엔진을 만들므로 풀 누수를 막기 위해 정리한다.
        if engine is not None:
            engine.dispose()


def run_pipeline(crawl_func=crawl_all) -> Path | None:
    # 로컬 raw 파일 + DB 적재본 URL의 합집합으로 거른다.
    # → 이미 DB에 들어간 항목은 재저장·재업로드·재태깅하지 않는다(LLM 비용 절감).
    existing_urls = load_existing_urls() | load_existing_urls_from_db()
    items = crawl_func()
    new_items = filter_existing_urls(items, existing_urls)
    new_items = dedupe_by_url(new_items)

    logger.info(
        "Filtered against existing raw data + DB. crawled=%s new=%s",
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

    # 저장·업로드 후 적재(태깅→임베딩→DB). 실패해도 크롤은 유지.
    _maybe_ingest(new_items)
    return saved_path


def main() -> None:
    run_pipeline(crawl_all)


if __name__ == "__main__":
    main()
# 팀 아키텍처 규칙 반영 완료 - 규원
