"""HIVE-100 인증 단위 테스트: 비밀번호 해시 · JWT · 로그인 · get_current_user(IDOR 봉합).

핵심: secret 없이는 유효 토큰을 만들 수 없으므로, 피해자 id를 알아도 세션을 위조할 수 없다.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import jwt as pyjwt
import pytest
from fastapi import Depends, FastAPI, status
from fastapi.testclient import TestClient

from app.config import settings

# 토큰 발급/검증 secret 주입(테스트용)
settings.jwt_secret = "test-secret-hive100"

from app.api.auth import get_current_user
from app.api.auth import router as auth_router
from app.database import get_db
from app.services.rate_limit import reset_all_for_testing
from app.services.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


# ── 비밀번호 해시 ─────────────────────────────────────────────────────────

def test_password_hash_roundtrip():
    h = hash_password("s3cret-pass")
    assert h != "s3cret-pass"                 # 평문 저장 안 함
    assert verify_password("s3cret-pass", h)
    assert not verify_password("wrong-pass", h)


def test_verify_legacy_null_hash_always_fails():
    # 레거시 계정(password_hash NULL/빈값) → 로그인 불가
    assert not verify_password("anything", None)
    assert not verify_password("anything", "")


# ── JWT 서명/위조 ─────────────────────────────────────────────────────────

def test_token_roundtrip():
    assert decode_access_token(create_access_token(42)) == 42


def test_forged_token_other_secret_rejected():
    # 공격자가 자기 secret으로 user 1 토큰 위조 → 서버 secret 검증에서 거부 (IDOR 핵심)
    forged = pyjwt.encode({"sub": "1"}, "attacker-secret", algorithm="HS256")
    with pytest.raises(pyjwt.InvalidTokenError):
        decode_access_token(forged)


def test_tampered_token_rejected():
    with pytest.raises(pyjwt.InvalidTokenError):
        decode_access_token(create_access_token(7) + "tamper")


def test_expired_token_rejected(monkeypatch):
    monkeypatch.setattr(settings, "jwt_expire_hours", -1)   # 이미 만료
    tok = create_access_token(7)
    monkeypatch.setattr(settings, "jwt_expire_hours", 336)
    with pytest.raises(pyjwt.ExpiredSignatureError):
        decode_access_token(tok)


# ── get_current_user (Bearer) ─────────────────────────────────────────────

_app = FastAPI()


@_app.get("/whoami")
def _whoami(user=Depends(get_current_user)):
    return {"id": user.id}


def _client(db_user):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = db_user
    _app.dependency_overrides[get_db] = lambda: db
    return TestClient(_app, raise_server_exceptions=False)


def test_get_current_user_valid_token():
    client = _client(SimpleNamespace(id=5))
    res = client.get("/whoami", headers={"Authorization": f"Bearer {create_access_token(5)}"})
    assert res.status_code == status.HTTP_200_OK and res.json()["id"] == 5


def test_get_current_user_no_token_401():
    client = _client(SimpleNamespace(id=5))
    assert client.get("/whoami").status_code == status.HTTP_401_UNAUTHORIZED


def test_get_current_user_forged_token_401():
    # DB에 user 1이 존재해도, 위조 서명 토큰은 거부 → 타인 사칭 차단
    client = _client(SimpleNamespace(id=1))
    forged = pyjwt.encode({"sub": "1"}, "attacker-secret", algorithm="HS256")
    res = client.get("/whoami", headers={"Authorization": f"Bearer {forged}"})
    assert res.status_code == status.HTTP_401_UNAUTHORIZED


# ── 로그인 엔드포인트 ──────────────────────────────────────────────────────

_authapp = FastAPI()
_authapp.include_router(auth_router)


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    reset_all_for_testing()
    yield
    reset_all_for_testing()


def _login_client(db_user):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = db_user
    _authapp.dependency_overrides[get_db] = lambda: db
    return TestClient(_authapp, raise_server_exceptions=False)


def _fake_user():
    return SimpleNamespace(
        id=1, username="alice", password_hash=hash_password("correct-horse"),
        display_name="Alice", persona="개발자", current_level="입문",
    )


def test_login_ok_returns_signed_token():
    client = _login_client(_fake_user())
    res = client.post("/auth/login", json={"username": "alice", "password": "correct-horse"})
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["token_type"] == "bearer"
    assert decode_access_token(body["access_token"]) == 1


def test_login_wrong_password_401():
    client = _login_client(_fake_user())
    res = client.post("/auth/login", json={"username": "alice", "password": "WRONG"})
    assert res.status_code == status.HTTP_401_UNAUTHORIZED


def test_login_unknown_user_401():
    client = _login_client(None)   # 아이디 없음
    res = client.post("/auth/login", json={"username": "ghost", "password": "whatever"})
    assert res.status_code == status.HTTP_401_UNAUTHORIZED


def test_login_legacy_null_hash_401():
    # 레거시 계정(password_hash NULL)은 로그인 불가 — 더미 bcrypt 경로로 timing도 동일화
    legacy = SimpleNamespace(
        id=2, username="legacy", password_hash=None,
        display_name="Legacy", persona="개발자", current_level="입문",
    )
    client = _login_client(legacy)
    res = client.post("/auth/login", json={"username": "legacy", "password": "whatever"})
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
