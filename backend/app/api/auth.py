"""데모용 프로필 선택 세션.

정식 인증(JWT/OAuth)을 구현하지 않는다. 유저는 display_name과 persona를 입력하여
프로필을 생성하고, 이후 요청은 X-User-Id 헤더로 자신을 식별한다.
"""

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


class ProfileCreate(BaseModel):
    display_name: str
    persona: str = "개발자"


class ProfileResponse(BaseModel):
    user_id: int
    display_name: str
    persona: str

    class Config:
        from_attributes = True


@router.post("/profile", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED)
def create_profile(payload: ProfileCreate, db: Session = Depends(get_db)) -> ProfileResponse:
    user = User(display_name=payload.display_name, persona=payload.persona)
    db.add(user)
    db.commit()
    db.refresh(user)
    return ProfileResponse(user_id=user.id, display_name=user.display_name, persona=user.persona)


@router.get("/profile/{user_id}", response_model=ProfileResponse)
def get_profile(user_id: int, db: Session = Depends(get_db)) -> ProfileResponse:
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="profile not found")
    return ProfileResponse(user_id=user.id, display_name=user.display_name, persona=user.persona)


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
