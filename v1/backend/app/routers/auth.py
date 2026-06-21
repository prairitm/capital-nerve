from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.db.enums import UserType
from app.models.user import AppUser, Watchlist
from app.schemas.auth import LoginRequest, SignupRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue_token(user: AppUser) -> TokenResponse:
    token = create_access_token(user.user_id, extra={"email": user.email, "type": user.user_type.value})
    return TokenResponse(
        access_token=token,
        user_id=user.user_id,
        email=user.email or "",
        user_type=user.user_type,
        full_name=user.full_name,
    )


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest, db: Session = Depends(get_db)) -> TokenResponse:
    existing = db.scalar(select(AppUser).where(AppUser.email == body.email))
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email already exists.")
    user = AppUser(
        email=body.email,
        full_name=body.full_name,
        hashed_password=hash_password(body.password),
        user_type=UserType.RETAIL,
    )
    db.add(user)
    db.flush()
    db.add(Watchlist(user_id=user.user_id, watchlist_name="Default Watchlist"))
    db.commit()
    db.refresh(user)
    return _issue_token(user)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(AppUser).where(AppUser.email == body.email))
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return _issue_token(user)


@router.get("/me", response_model=UserResponse)
def me(user: AppUser = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(user)
