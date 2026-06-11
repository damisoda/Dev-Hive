from __future__ import annotations

import logging
from threading import Lock

from app.crawler.run_crawler import crawl_github, crawl_reddit, crawl_velog, run_pipeline

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


def run_github_job() -> None:
    _run_named_pipeline("github_12h", crawl_github)


def run_reddit_job() -> None:
    _run_named_pipeline("reddit_24h", crawl_reddit)


def run_velog_job() -> None:
    _run_named_pipeline("velog_24h", crawl_velog)


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
        if not _scheduler.running:
            _scheduler.start()
            logger.info("Crawler scheduler started")
    return _scheduler


def stop_scheduler() -> None:
    with _scheduler_lock:
        if _scheduler is not None and _scheduler.running:
            _scheduler.shutdown(wait=False)
            logger.info("Crawler scheduler stopped")
