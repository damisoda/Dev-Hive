import json
import logging
import os
import time
import traceback
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import auth, content, feedback, graph, progress, recommend, stats
from app.crawler.scheduler import start_scheduler, stop_scheduler
from app.database import get_db

_SCHEDULER_ENABLED = os.getenv("ENABLE_SCHEDULER", "").lower() in ("1", "true", "yes")


# ── Structured logging ────────────────────────────────────────────────────────
class _StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _configure_logging() -> None:
    fmt = _StructuredFormatter()
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        lgr = logging.getLogger(name)
        lgr.handlers.clear()
        handler = logging.StreamHandler()
        handler.setFormatter(fmt)
        lgr.addHandler(handler)
        lgr.propagate = False
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(fmt)
    root.addHandler(handler)
    root.setLevel(logging.INFO)


_configure_logging()
logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────
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


# ── CORS ──────────────────────────────────────────────────────────────────────
_CORS_ORIGINS: list[str] = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://dev-hive.vercel.app",
]

_extra = os.getenv("CORS_ORIGINS", "")
if _extra:
    _CORS_ORIGINS.extend(o.strip() for o in _extra.split(",") if o.strip())

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_origin_regex=r"https://dev-hive-.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Access-log middleware ─────────────────────────────────────────────────────
class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        t0 = time.perf_counter()
        response = await call_next(request)
        ms = round((time.perf_counter() - t0) * 1000, 1)
        logger.info(
            json.dumps(
                {
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "ms": ms,
                    "ip": request.client.host if request.client else "-",
                },
                ensure_ascii=False,
            )
        )
        return response


app.add_middleware(AccessLogMiddleware)


# ── Global exception handler ──────────────────────────────────────────────────
@app.exception_handler(Exception)
async def _global_exception_handler(request: Request, _exc: Exception):
    logger.error(
        json.dumps(
            {
                "event": "unhandled_exception",
                "path": request.url.path,
                "exc": traceback.format_exc(),
            },
            ensure_ascii=False,
        )
    )
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as exc:
        logger.error(json.dumps({"event": "health_db_fail", "exc": str(exc)}))
        return JSONResponse(status_code=503, content={"status": "db_unavailable"})


app.include_router(auth.router)
app.include_router(content.router)
app.include_router(recommend.router)
app.include_router(progress.router)
app.include_router(graph.router)
app.include_router(feedback.router)
app.include_router(stats.router)
