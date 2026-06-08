from __future__ import annotations

import logging
from threading import Lock

from apscheduler.schedulers.background import BackgroundScheduler

from app.crawler.run_crawler import crawl_github_hn, crawl_reddit_rss, run_pipeline

logger = logging.getLogger(__name__)

_scheduler_lock = Lock()
scheduler = BackgroundScheduler(timezone="Asia/Seoul")


def _run_named_pipeline(name: str, crawl_func) -> None:
    logger.info("Scheduled crawler job started: %s", name)
    try:
        saved_path = run_pipeline(crawl_func)
        logger.info("Scheduled crawler job finished: %s saved_path=%s", name, saved_path)
    except Exception:
        logger.exception("Scheduled crawler job failed: %s", name)


def run_github_hn_job() -> None:
    _run_named_pipeline("github_hackernews_12h", crawl_github_hn)


def run_reddit_rss_job() -> None:
    _run_named_pipeline("reddit_rss_24h", crawl_reddit_rss)


def start_scheduler() -> BackgroundScheduler:
    with _scheduler_lock:
        if not scheduler.get_job("github_hackernews_12h"):
            scheduler.add_job(
                run_github_hn_job,
                trigger="interval",
                hours=12,
                id="github_hackernews_12h",
                max_instances=1,
                coalesce=True,
                replace_existing=True,
            )
        if not scheduler.get_job("reddit_rss_24h"):
            scheduler.add_job(
                run_reddit_rss_job,
                trigger="interval",
                hours=24,
                id="reddit_rss_24h",
                max_instances=1,
                coalesce=True,
                replace_existing=True,
            )
        if not scheduler.running:
            scheduler.start()
            logger.info("Crawler scheduler started")
    return scheduler


def stop_scheduler() -> None:
    with _scheduler_lock:
        if scheduler.running:
            scheduler.shutdown(wait=False)
            logger.info("Crawler scheduler stopped")
