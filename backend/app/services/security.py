"""HIVE-100: 비밀번호 해시 + JWT 토큰. 인증의 단일 신뢰 지점.

- 비밀번호: bcrypt 해시/검증 (평문은 저장하지 않음).
- 세션: HS256 JWT. payload `sub`=user_id, `exp`=만료. get_current_user가 서명을 검증해
  X-User-Id 같은 위조 가능 식별자를 대체한다(= IDOR 실봉합의 핵심).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings

_ALG = "HS256"
_BCRYPT_MAX_BYTES = 72  # bcrypt 입력 한계. 초과분은 잘린다 → 가입 단에서 길이 제한도 검증.


def hash_password(password: str) -> str:
    pw = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str | None) -> bool:
    """평문↔해시 비교. 해시가 없으면(레거시 계정) 항상 실패 → 로그인 불가."""
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(
            password.encode("utf-8")[:_BCRYPT_MAX_BYTES],
            password_hash.encode("utf-8"),
        )
    except ValueError:
        return False


def create_access_token(user_id: int) -> str:
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET 미설정 — 토큰을 발급할 수 없습니다(.env 주입 필요).")
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(hours=settings.jwt_expire_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALG)


def decode_access_token(token: str) -> int:
    """유효 토큰의 user_id 반환. 서명불일치/만료/형식오류는 예외를 올린다.

    위조(임의 X-User-Id 류)는 서명 검증에서 막힌다 — secret 없이는 토큰을 만들 수 없다.
    """
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET 미설정 — 토큰을 검증할 수 없습니다.")
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[_ALG])
    return int(payload["sub"])
