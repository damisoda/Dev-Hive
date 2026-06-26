import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

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

# ──────────────────────────────────────────────────────────────────────────────
# HIVE-64: CORS 미들웨어
# allow_origins: 로컬 개발(localhost:3000 / 127.0.0.1:3000) + Vercel 프로덕션 도메인.
#   - VERCEL_URL 환경변수가 있으면 런타임에 자동 삽입; 없으면 정적 목록만 사용.
# allow_credentials=True: 쿠키(dh_token httpOnly) 기반 세션·인증을 위한 필수 옵션.
# allow_methods/allow_headers=["*"]: 라우팅·프리플라이트 차단 방지.
# ──────────────────────────────────────────────────────────────────────────────
_CORS_ORIGINS: list[str] = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    # Vercel 프로덕션 도메인 — 배포 후 실제 URL로 교체하거나 CORS_ORIGINS 환경변수로 주입
    "https://dev-hive.vercel.app",
]

# CORS_ORIGINS 환경변수(쉼표 구분)를 통해 런타임에 추가 origin 주입 가능
_extra = os.getenv("CORS_ORIGINS", "")
if _extra:
    _CORS_ORIGINS.extend(o.strip() for o in _extra.split(",") if o.strip())

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,   # 쿠키·인증 헤더 허용 (Mastery/Profile 세션 연동 필수)
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    # API 서버 루트 = 404 대신 Swagger 문서로 안내 (브라우저 직접 방문 대비)
    return RedirectResponse(url="/docs")


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
