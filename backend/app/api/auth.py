"""데모용 프로필 선택 세션.

정식 인증(JWT/OAuth)을 구현하지 않는다. 유저는 display_name과 persona를 입력하여
프로필을 생성하고, 이후 요청은 X-User-Id 헤더로 자신을 식별한다.
"""

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])

# 온보딩 자가평가 문항 키 (프론트의 질문 순서와 1:1 대응).
# 각 답변은 0~2점이며, 합산 점수로 초기 current_level을 정한다.
ONBOARDING_QUESTION_KEYS = ("ai_tool_usage", "llm_understanding", "advanced_topics")


def compute_initial_level(answers: dict[str, int]) -> str:
    """3문항 자가평가 점수(문항당 0~2)를 합산하여 초기 레벨을 산정한다.

    0~1 → 입문, 2~4 → 중급, 5~6 → 고급.
    누락/범위 밖 값은 0~2로 보정하여 방어한다.
    """
    total = sum(
        min(max(int(answers.get(key, 0)), 0), 2)
        for key in ONBOARDING_QUESTION_KEYS
    )
    if total <= 1:
        return "입문"
    if total <= 4:
        return "중급"
    return "고급"


class ProfileCreate(BaseModel):
    display_name: str
    persona: str = "개발자"
    onboarding_answers: dict[str, int] = Field(default_factory=dict)


class ProfileResponse(BaseModel):
    user_id: int
    display_name: str
    persona: str
    current_level: str

    class Config:
        from_attributes = True


@router.post("/profile", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED)
def create_profile(payload: ProfileCreate, db: Session = Depends(get_db)) -> ProfileResponse:
    level = compute_initial_level(payload.onboarding_answers)
    user = User(
        display_name=payload.display_name,
        persona=payload.persona,
        onboarding_answers=payload.onboarding_answers or None,
        current_level=level,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
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
