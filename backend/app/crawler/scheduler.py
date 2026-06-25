from __future__ import annotations

import logging
from threading import Lock

from app.crawler.run_crawler import (
    crawl_github,
    crawl_github_discussions,
    crawl_huggingface,
    crawl_reddit,
    crawl_reddit_public,
    crawl_velog,
    crawl_velog_beginner,
    crawl_x,
    run_pipeline,
)

logger = logging.getLogger(__name__)

_scheduler_lock = Lock()
# apscheduler는 스케줄러를 실제로 켤 때(start_scheduler)만 import·생성한다(lazy).
# → app.main 임포트(= API·테스트)는 apscheduler 미설치여도 동작하고,
#   ENABLE_SCHEDULER=1로 스케줄러를 켤 때에만 의존성이 필요하다(opt-in 기능 = opt-in 의존성).
_scheduler = None


def _run_named_pipeline(name: str, crawl_func) -> None:
    logger.info("Scheduled crawler job started: %s", name)
    try:
        saved_path = run_pipeline(crawl_func)
        logger.info("Scheduled crawler job finished: %s saved_path=%s", name, saved_path)
    except Exception:
        logger.exception("Scheduled crawler job failed: %s", name)


def run_auto_hkg_job() -> None:
    """주기적 Auto-HKG 확장 — 미매핑 콘텐츠를 2패스로 그래프에 편입한다.

    크롤→적재 직후 _maybe_ingest에서도 호출되지만, 크롤 실패·일시 오류로
    누락된 콘텐츠를 48h마다 별도로 처리해 그래프 갱신 누락을 방지한다.
    """
    logger.info("Scheduled Auto-HKG job started")
    engine = None
    try:
        import os
        import anthropic
        from sqlalchemy import create_engine
        from app.graph.auto_hkg import expand_graph

        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        db_url = os.getenv("DATABASE_URL")
        if not (anthropic_key and db_url):
            logger.info("Auto-HKG 스킵 — ANTHROPIC_API_KEY 또는 DATABASE_URL 없음")
            return

        client = anthropic.Anthropic(api_key=anthropic_key)
        engine = create_engine(db_url)
        with engine.begin() as conn:
            stats = expand_graph(conn, client)
        logger.info(
            "Scheduled Auto-HKG 완료 — 처리:%s / 흡수:%s / 클러스터:%s / 고아:%s / 신규노드:%s / LLM:%s",
            stats["total"], stats["absorbed"], stats["clustered"],
            stats["orphan_mapped"], stats["new_nodes"], stats["llm_calls"],
        )
    except Exception:
        logger.exception("Scheduled Auto-HKG job failed")
    finally:
        if engine is not None:
            engine.dispose()


def run_github_job() -> None:
    _run_named_pipeline("github_12h", crawl_github)


def run_reddit_job() -> None:
    _run_named_pipeline("reddit_24h", crawl_reddit)


def run_velog_job() -> None:
    _run_named_pipeline("velog_24h", crawl_velog)


def run_reddit_public_job() -> None:
    _run_named_pipeline("reddit_public_24h", crawl_reddit_public)


def run_github_discussions_job() -> None:
    _run_named_pipeline("github_discussions_12h", crawl_github_discussions)


def run_x_job() -> None:
    _run_named_pipeline("x_24h", crawl_x)


def run_velog_beginner_job() -> None:
    _run_named_pipeline("velog_beginner_24h", crawl_velog_beginner)


def run_huggingface_job() -> None:
    _run_named_pipeline("huggingface_24h", crawl_huggingface)


def start_scheduler():
    """백그라운드 크롤 스케줄러 시작(idempotent). apscheduler를 여기서 lazy import한다."""
    global _scheduler
    from apscheduler.schedulers.background import BackgroundScheduler

    with _scheduler_lock:
        if _scheduler is None:
            _scheduler = BackgroundScheduler(timezone="Asia/Seoul")
        if not _scheduler.get_job("github_12h"):
            _scheduler.add_job(
                run_github_job,
                trigger="interval",
                hours=12,
                id="github_12h",
                max_instances=1,
                coalesce=True,
                replace_existing=True,
            )
        if not _scheduler.get_job("reddit_24h"):
            _scheduler.add_job(
                run_reddit_job,
                trigger="interval",
                hours=24,
                id="reddit_24h",
                max_instances=1,
                coalesce=True,
                replace_existing=True,
            )
        if not _scheduler.get_job("velog_24h"):
            _scheduler.add_job(
                run_velog_job,
                trigger="interval",
                hours=24,
                id="velog_24h",
                max_instances=1,
                coalesce=True,
                replace_existing=True,
            )
        if not _scheduler.get_job("reddit_public_24h"):
            _scheduler.add_job(
                run_reddit_public_job,
                trigger="interval",
                hours=24,
                id="reddit_public_24h",
                max_instances=1,
                coalesce=True,
                replace_existing=True,
            )
        if not _scheduler.get_job("github_discussions_12h"):
            _scheduler.add_job(
                run_github_discussions_job,
                trigger="interval",
                hours=12,
                id="github_discussions_12h",
                max_instances=1,
                coalesce=True,
                replace_existing=True,
            )
        if not _scheduler.get_job("x_24h"):
            _scheduler.add_job(
                run_x_job,
                trigger="interval",
                hours=24,
                id="x_24h",
                max_instances=1,
                coalesce=True,
                replace_existing=True,
            )
        if not _scheduler.get_job("velog_beginner_24h"):
            _scheduler.add_job(
                run_velog_beginner_job,
                trigger="interval",
                hours=24,
                id="velog_beginner_24h",
                max_instances=1,
                coalesce=True,
                replace_existing=True,
            )
        if not _scheduler.get_job("huggingface_24h"):
            _scheduler.add_job(
                run_huggingface_job,
                trigger="interval",
                hours=24,
                id="huggingface_24h",
                max_instances=1,
                coalesce=True,
                replace_existing=True,
            )
        if not _scheduler.get_job("auto_hkg_48h"):
            _scheduler.add_job(
                run_auto_hkg_job,
                trigger="interval",
                hours=48,
                id="auto_hkg_48h",
                max_instances=1,
                coalesce=True,
                replace_existing=True,
            )
        if not _scheduler.running:
            _scheduler.start()
            logger.info("Crawler scheduler started")
    return _scheduler


def stop_scheduler() -> None:
    with _scheduler_lock:
        if _scheduler is not None and _scheduler.running:
            _scheduler.shutdown(wait=False)
            logger.info("Crawler scheduler stopped")
