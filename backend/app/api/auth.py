"""HIVE-100: 아이디·비밀번호 회원가입/로그인 + JWT 세션.

회원가입 시 username/password로 계정을 만들고, 로그인하면 서명된 JWT를 받는다.
이후 요청은 `Authorization: Bearer <jwt>`로 본인을 증명한다 — get_current_user가
서명을 검증하므로 헤더 위조로 타인을 사칭할 수 없다(IDOR 봉합, HIVE-86 후속).
"""

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.services.constants import (
    DEFAULT_PERSONA,
    PERSONA_ONBOARDING,
)
from app.services.profile_vector import build_initial_vector, update_from_read_history
from app.services.rate_limit import (
    check_and_record_login_attempt,
    check_rate_limit,
    clear_login_failures,
)
from app.services.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# 미존재/레거시(해시 NULL) 계정 로그인 시도에도 bcrypt를 1회 수행해, 응답 시간으로
# 아이디 존재 여부가 새는 것을 막는다(timing 사이드채널 방어). 모듈 로드 시 1회 계산.
_DUMMY_PASSWORD_HASH = hash_password("dh-dummy-timing-equalizer")


def _coerce_score(value) -> int:
    """온보딩 답변 1개를 정수 점수로 안전 변환한다.

    비숫자/None 등 이상값은 0으로 본다. 레벨 계산·mastery·profile_vector가
    동일 JSONB를 각각 다시 파싱하므로, 여기서 한 번 정수로 정규화해 경로 간 해석을 맞춘다.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _sum_scores(answers: dict, key_max: dict[str, int]) -> int:
    """온보딩 답변을 점수 묶음별로 합산한다. 각 문항은 0~만점으로 클램프(방어)."""
    return sum(
        min(max(_coerce_score(answers.get(key)), 0), max_score)
        for key, max_score in key_max.items()
    )


def compute_initial_level(answers: dict[str, int], persona: str = DEFAULT_PERSONA) -> str:
    """온보딩 답변으로 초기 레벨을 산정한다 (HIVE-36).

    두 점수 묶음으로 환산(페르소나별 키 → 공통 로직):
      - ai_score(0~6): AI 숙련도 — 서비스 본질이 AI 학습이라 주축
      - baseline_score(0~5): 일반 개발 역량 — 시니어 보정에만 사용

    1) ai_score로 기본 레벨: 0~1 입문 / 2~4 중급 / 5~6 고급
    2) 시니어 보정: baseline이 시니어급이면 중급 상단(ai_score==4)에서만 → 고급.
       입문 구간(0~1)은 시니어여도 입문 고정 — AI 기초 없으면 콘텐츠를 못 따라감.
    """
    cfg = PERSONA_ONBOARDING.get(persona, PERSONA_ONBOARDING[DEFAULT_PERSONA])
    ai_score = _sum_scores(answers, cfg["ai_keys"])
    baseline_score = _sum_scores(answers, cfg["baseline_keys"])

    ai_beginner_max = cfg["ai_beginner_max"]
    ai_mid_max = cfg["ai_mid_max"]
    if ai_score <= ai_beginner_max:
        base = "입문"
    elif ai_score <= ai_mid_max:
        base = "중급"
    else:
        base = "고급"

    # 시니어 보정: 중급 상단(ai_score == ai_mid_max)에서만 +1단계.
    # 입문 구간은 보정 안 함(위 base가 입문이면 아래 조건이 거짓).
    if baseline_score >= cfg["senior_baseline_min"] and ai_score == ai_mid_max:
        return "고급"
    return base


class ProfileCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
    persona: str = DEFAULT_PERSONA
    onboarding_answers: dict[str, int] = Field(default_factory=dict)

    @field_validator("persona")
    @classmethod
    def _validate_persona(cls, v: str) -> str:
        # 등록된 페르소나만 허용 — 임의 문자열이 DB에 저장되는 것 방지
        if v not in PERSONA_ONBOARDING:
            raise ValueError(
                f"unknown persona: {v!r} (allowed: {list(PERSONA_ONBOARDING)})"
            )
        return v

    @field_validator("onboarding_answers")
    @classmethod
    def _validate_answers(cls, v: dict[str, int]) -> dict[str, int]:
        # 답변 점수 범위 방어 (0~9). 키별 만점 클램프는 _sum_scores가 하지만,
        # 음수/과도값이 DB에 그대로 저장되지 않도록 입력 단에서 1차 차단.
        for key, score in v.items():
            if not isinstance(score, int) or not (0 <= score <= 9):
                raise ValueError(f"invalid onboarding score for {key!r}: {score!r}")
        return v


class SignupRequest(ProfileCreate):
    """회원가입 = 기존 프로필(display_name·persona·온보딩) + 로그인 자격(아이디·비번)."""

    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=72)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=72)


class ProfileResponse(BaseModel):
    user_id: int
    display_name: str
    persona: str
    current_level: str

    class Config:
        from_attributes = True




class EditableProfileResponse(ProfileResponse):
    onboarding_answers: dict[str, int] = Field(default_factory=dict)


class ProfileUpdate(ProfileCreate):
    """로그인 후 정보 수정 = 회원가입 온보딩 프로필의 재저장."""


class AuthResponse(BaseModel):
    """가입/로그인 성공 시 JWT + 프로필 요약. 클라이언트(BFF)는 토큰을 httpOnly 쿠키로 저장."""

    access_token: str
    token_type: str = "bearer"
    user_id: int
    display_name: str
    persona: str
    current_level: str


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(request: Request, payload: SignupRequest, db: Session = Depends(get_db)) -> AuthResponse:
    """아이디·비번 + 온보딩으로 계정 생성 후 JWT 발급. 중복 아이디는 409."""
    ip = request.client.host if request.client else "unknown"
    check_rate_limit(f"signup:{ip}", limit=10, window_seconds=3600, detail="가입 요청이 너무 많습니다.")
    level = compute_initial_level(payload.onboarding_answers, payload.persona)
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name,
        persona=payload.persona,
        onboarding_answers=payload.onboarding_answers or None,
        current_level=level,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # username UNIQUE 위반(동시 가입 레이스 포함) → 409
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 사용 중인 아이디입니다.")
    db.refresh(user)

    # 온보딩 답변 기반 profile_vector 초기값 설정 (HIVE-30)
    if payload.onboarding_answers:
        build_initial_vector(user.id, payload.onboarding_answers, db)

    return AuthResponse(
        access_token=create_access_token(user.id),
        user_id=user.id,
        display_name=user.display_name,
        persona=user.persona,
        current_level=user.current_level,
    )


@router.post("/login", response_model=AuthResponse)
def login(request: Request, payload: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    """아이디·비번 검증 후 JWT 발급. 실패 시 401(아이디 존재 여부 노출 안 함)."""
    ip = request.client.host if request.client else "unknown"
    check_rate_limit(f"login:{ip}", limit=5, window_seconds=60, detail="요청이 너무 많습니다.")
    # 잠금 확인 + 실패 기록을 원자적으로 수행 (TOCTOU 방지).
    # 성공 로그인 시 clear_login_failures로 여기서 기록한 타임스탬프를 지운다.
    check_and_record_login_attempt(payload.username)
    user = db.query(User).filter(User.username == payload.username).first()
    if user is None or not user.password_hash:
        # 미존재/레거시 계정도 동일한 bcrypt 비용을 치르게 해 timing 차이를 없앤다.
        verify_password(payload.password, _DUMMY_PASSWORD_HASH)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials"
        )
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials"
        )
    clear_login_failures(payload.username)
    return AuthResponse(
        access_token=create_access_token(user.id),
        user_id=user.id,
        display_name=user.display_name,
        persona=user.persona,
        current_level=user.current_level,
    )


@router.get("/profile/{user_id}", response_model=ProfileResponse)
def get_profile(user_id: int, db: Session = Depends(get_db)) -> ProfileResponse:
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="profile not found")
    return ProfileResponse(
        user_id=user.id,
        display_name=user.display_name,
        persona=user.persona,
        current_level=user.current_level,
    )


def get_current_user(
    authorization: str | None = Header(None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> User:
    """`Authorization: Bearer <jwt>`의 서명을 검증해 현재 유저를 주입한다.

    토큰 누락/만료/위조는 401. secret 없이는 토큰을 만들 수 없으므로 타인 id로
    토큰을 위조할 수 없다 — 위조 가능한 X-User-Id 신뢰 방식의 IDOR를 봉합한다(HIVE-86 후속).
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token"
        )
    token = authorization.split(" ", 1)[1].strip()
    try:
        user_id = decode_access_token(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or expired token"
        )
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid user")
    return user


def _editable_profile_response(user: User) -> EditableProfileResponse:
    return EditableProfileResponse(
        user_id=user.id,
        display_name=user.display_name,
        persona=user.persona,
        current_level=user.current_level,
        onboarding_answers=user.onboarding_answers or {},
    )


@router.get("/me", response_model=EditableProfileResponse)
def get_me(current_user: User = Depends(get_current_user)) -> EditableProfileResponse:
    """현재 로그인 사용자의 수정 가능한 프로필을 조회한다."""
    return _editable_profile_response(current_user)


@router.patch("/me", response_model=EditableProfileResponse)
def update_me(
    payload: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EditableProfileResponse:
    """온보딩 프로필을 수정하고 개인화 레벨·추천 벡터를 재계산한다."""
    answers = payload.onboarding_answers or {}
    current_user.display_name = payload.display_name
    current_user.persona = payload.persona
    current_user.onboarding_answers = answers or None
    current_user.current_level = compute_initial_level(answers, payload.persona)
    db.add(current_user)
    db.commit()
    db.refresh(current_user)

    update_from_read_history(current_user.id, db)
    db.refresh(current_user)
    return _editable_profile_response(current_user)
