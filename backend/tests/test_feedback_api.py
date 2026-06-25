"""HIVE-100 feedback API 인증/IDOR 테스트.

get_current_user(Bearer JWT) 연결 후:
- Authorization 헤더 없음 → 401
- 서명은 유효하나 유저 미존재 → 401
- 정상 e2e: set → list → clear → list
- IDOR 방어: payload/query에 타인 user_id를 넣어도 토큰의 본인 ID로만 동작.

HIVE-100으로 토큰이 서명되어(secret 없이는 발급 불가) 타인 id 위조가 차단된다 —
기존 X-User-Id 신뢰 방식의 IDOR 한계가 봉합됨.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.api.feedback import router
from app.api.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.services.security import create_access_token

from fastapi import FastAPI

# 토큰 발급/검증에 필요한 secret을 테스트용으로 주입
settings.jwt_secret = "test-secret-hive100"

# 최소 앱 구성 — feedback 라우터만 마운트
_app = FastAPI()
_app.include_router(router)


def _make_user(uid: int):
    u = MagicMock()
    u.id = uid
    return u


def _make_db(rows=None):
    """fetchall / execute / commit을 흉내낸 가짜 Session."""
    db = MagicMock()
    result = MagicMock()
    result.fetchall.return_value = rows or []
    db.execute.return_value = result
    return db


def _client_as(uid: int, db=None):
    """uid 유저로 인증된 TestClient. DB도 주입 가능."""
    if db is None:
        db = _make_db()
    _app.dependency_overrides[get_current_user] = lambda: _make_user(uid)
    _app.dependency_overrides[get_db] = lambda: db
    return TestClient(_app, raise_server_exceptions=False)


def _client_no_auth(db=None):
    """토큰 없이 원본 get_current_user를 유지하는 TestClient."""
    if db is None:
        db = _make_db()
    _app.dependency_overrides.pop(get_current_user, None)
    _app.dependency_overrides[get_db] = lambda: db
    return TestClient(_app, raise_server_exceptions=False)


# ── 토큰 없음 / 유저 미존재 ──────────────────────────────────────────────

def test_missing_token_returns_401():
    client = _client_no_auth()
    # Authorization 헤더 없이 PUT → get_current_user가 401(토큰 누락)
    res = client.put("/feedback", json={"content_id": 1, "feedback": "understood"})
    assert res.status_code == status.HTTP_401_UNAUTHORIZED


def test_invalid_user_returns_401():
    # 서명은 유효하나 DB에 없는 user_id 토큰 → 401
    db = _make_db()
    db.query.return_value.filter.return_value.first.return_value = None
    _app.dependency_overrides.pop(get_current_user, None)
    _app.dependency_overrides[get_db] = lambda: db
    client = TestClient(_app, raise_server_exceptions=False)
    token = create_access_token(99999)
    res = client.put(
        "/feedback",
        json={"content_id": 1, "feedback": "understood"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == status.HTTP_401_UNAUTHORIZED


# ── 정상 e2e ─────────────────────────────────────────────────────────────

def test_set_feedback_ok():
    db = _make_db()
    # _ensure_exists: user / content 모두 존재
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(id=1)
    client = _client_as(uid=1, db=db)
    res = client.put("/feedback", json={"content_id": 10, "feedback": "understood"})
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["feedback"] == "understood"


def test_clear_feedback_ok():
    db = _make_db()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(id=1)
    client = _client_as(uid=1, db=db)
    res = client.request("DELETE", "/feedback", json={"content_id": 10})
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["feedback"] is None


def test_list_feedback_ok():
    rows = [SimpleNamespace(content_id=10, feedback="understood")]
    db = _make_db(rows=rows)
    client = _client_as(uid=1, db=db)
    res = client.get("/feedback")
    assert res.status_code == status.HTTP_200_OK
    assert res.json() == {"10": "understood"}


# ── IDOR 방어: payload의 user_id는 무시되고 헤더 uid로만 동작 ────────────

def test_set_feedback_uses_header_uid_not_payload():
    """payload에 타인 user_id(B=99)를 넣어도 헤더 uid(A=1)로만 INSERT된다."""
    db = _make_db()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(id=1)
    client = _client_as(uid=1, db=db)
    # 구 스키마처럼 user_id=99를 body에 넣어도 모델에서 무시됨(extra field)
    res = client.put(
        "/feedback",
        json={"user_id": 99, "content_id": 10, "feedback": "understood"},
    )
    assert res.status_code == status.HTTP_200_OK
    # DB execute 호출 시 uid=1(헤더)로만 전달됐는지 확인
    call_kwargs = db.execute.call_args_list[-1]
    params = call_kwargs[0][1]
    assert params["uid"] == 1


def test_list_feedback_uses_header_uid_not_query():
    """query param으로 타인 uid를 넣어도 헤더 uid(1)의 피드백만 조회된다."""
    rows = [SimpleNamespace(content_id=10, feedback="want_more")]
    db = _make_db(rows=rows)
    client = _client_as(uid=1, db=db)
    # 구 스키마처럼 ?user_id=99를 붙여도 무시됨
    res = client.get("/feedback?user_id=99")
    assert res.status_code == status.HTTP_200_OK
    call_kwargs = db.execute.call_args_list[-1]
    params = call_kwargs[0][1]
    assert params["uid"] == 1
