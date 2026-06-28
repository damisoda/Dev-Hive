"""main.py 고도화 검증: CORS · 전역 예외핸들러 · 접근 로그 미들웨어 · /health DB 체크."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ── 앱 픽스처 ─────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def client():
    """실제 app을 임포트하되, DB 의존성만 Mock으로 교체."""
    from app.database import get_db
    from app.main import app

    mock_db = MagicMock()
    mock_db.execute.return_value = None  # SELECT 1 정상 반환

    app.dependency_overrides[get_db] = lambda: mock_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


# ── /health ───────────────────────────────────────────────────────────────────

def test_health_200_with_db(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_health_503_when_db_fails():
    from app.database import get_db
    from app.main import app

    def broken_db():
        db = MagicMock()
        db.execute.side_effect = Exception("connection refused")
        return db

    app.dependency_overrides[get_db] = broken_db
    with TestClient(app, raise_server_exceptions=False) as c:
        res = c.get("/health")
    app.dependency_overrides.clear()

    assert res.status_code == 503
    assert res.json()["status"] == "db_unavailable"


# ── 전역 예외 핸들러 ───────────────────────────────────────────────────────────

def test_global_exception_handler_returns_500_json():
    """처리되지 않은 예외가 발생하면 {"detail": "Internal Server Error"} + 500."""
    from app.database import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: MagicMock()

    # 폭탄 라우트를 임시 등록
    @app.get("/test-bomb")
    def _bomb():
        raise RuntimeError("kaboom")

    with TestClient(app, raise_server_exceptions=False) as c:
        res = c.get("/test-bomb")

    app.dependency_overrides.clear()

    assert res.status_code == 500
    assert res.json() == {"detail": "Internal Server Error"}


# ── CORS ──────────────────────────────────────────────────────────────────────

def test_cors_localhost_allowed(client):
    res = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert res.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_cors_vercel_static_allowed(client):
    res = client.get("/health", headers={"Origin": "https://dev-hive.vercel.app"})
    assert res.headers.get("access-control-allow-origin") == "https://dev-hive.vercel.app"


def test_cors_vercel_wildcard_allowed(client):
    """Vercel 프리뷰 배포 URL(dev-hive-*.vercel.app)도 허용돼야 한다."""
    origin = "https://dev-hive-pr-42.vercel.app"
    res = client.options(
        "/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res.headers.get("access-control-allow-origin") == origin


def test_cors_credentials_header(client):
    res = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert res.headers.get("access-control-allow-credentials") == "true"


def test_cors_unknown_origin_blocked(client):
    res = client.get("/health", headers={"Origin": "https://evil.com"})
    # 허용되지 않은 origin은 ACAO 헤더 자체가 없어야 함
    assert "access-control-allow-origin" not in res.headers


# ── 루트 리다이렉트 ───────────────────────────────────────────────────────────

def test_root_redirects_to_docs(client):
    res = client.get("/", follow_redirects=False)
    assert res.status_code in (301, 302, 307, 308)
    assert res.headers["location"].endswith("/docs")


# ── 접근 로그 미들웨어 ─────────────────────────────────────────────────────────

def test_access_log_middleware_does_not_break_response(client):
    """/health 요청이 미들웨어를 거쳐도 정상 응답을 반환한다."""
    res = client.get("/health")
    assert res.status_code == 200
