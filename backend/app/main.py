from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import auth, content, progress, recommend
from app.crawler.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    try:
        yield
    finally:
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
