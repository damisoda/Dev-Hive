"""데모용 프로필 선택 세션.

정식 인증(JWT/OAuth)을 구현하지 않는다. 유저는 display_name과 persona를 입력하여
프로필을 생성하고, 이후 요청은 X-User-Id 헤더로 자신을 식별한다.
"""

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.services.constants import (
    DEFAULT_PERSONA,
    PERSONA_ONBOARDING,
)
from app.services.profile_vector import build_initial_vector

router = APIRouter(prefix="/auth", tags=["auth"])


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


class ProfileResponse(BaseModel):
    user_id: int
    display_name: str
    persona: str
    current_level: str

    class Config:
        from_attributes = True


@router.post("/profile", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED)
def create_profile(payload: ProfileCreate, db: Session = Depends(get_db)) -> ProfileResponse:
    level = compute_initial_level(payload.onboarding_answers, payload.persona)
    user = User(
        display_name=payload.display_name,
        persona=payload.persona,
        onboarding_answers=payload.onboarding_answers or None,
        current_level=level,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # 온보딩 답변 기반 profile_vector 초기값 설정 (HIVE-30)
    if payload.onboarding_answers:
        build_initial_vector(user.id, payload.onboarding_answers, db)

    return ProfileResponse(
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
    x_user_id: int = Header(..., alias="X-User-Id"),
    db: Session = Depends(get_db),
) -> User:
    """이후 라우터에서 현재 유저를 주입받기 위한 의존성.

    클라이언트는 모든 인증 필요 요청에 `X-User-Id: {user_id}` 헤더를 포함한다.
    """
    user = db.query(User).filter(User.id == x_user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid user")
    return user
