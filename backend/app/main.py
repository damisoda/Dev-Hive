import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import auth, content, feedback, graph, progress, recommend, stats
from app.crawler.scheduler import start_scheduler, stop_scheduler

# 스케줄러는 명시적 opt-in(ENABLE_SCHEDULER=1)일 때만 자동 가동한다.
# 테스트/데모/단일 실행에서 백그라운드 크롤러가 멋대로 도는 것을 방지(HIVE-35 머지 시 추가).
_SCHEDULER_ENABLED = os.getenv("ENABLE_SCHEDULER", "").lower() in ("1", "true", "yes")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if _SCHEDULER_ENABLED:
        start_scheduler()
    try:
        yield
    finally:
        if _SCHEDULER_ENABLED:
            stop_scheduler()


app = FastAPI(title="Dev-Hive API", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


# 라우터 등록
app.include_router(auth.router)
app.include_router(content.router)
app.include_router(recommend.router)
app.include_router(progress.router)
app.include_router(graph.router)
app.include_router(feedback.router)
app.include_router(stats.router)
