from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models.user import User, UserRole
from schemas.auth import LoginRequest, RefreshRequest, TokenResponse
from schemas.user import UserRead
from services.auth_service import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from dependencies.auth import get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


DEFAULT_USERS = [
    {
        "username_setting": "admin_username",
        "password_setting": "admin_password",
        "name": "Администратор",
        "role": UserRole.admin,
    },
    {
        "username_setting": "kitchen_username",
        "password_setting": "kitchen_password",
        "name": "Старший повар",
        "role": UserRole.kitchen,
    },
    {
        "username_setting": "partner_username",
        "password_setting": "partner_password",
        "name": "Партнёр",
        "role": UserRole.partner,
    },
]


def seed_default_users(db: Session) -> None:
    """Idempotent: only inserts users that don't yet exist."""
    for entry in DEFAULT_USERS:
        username = getattr(settings, entry["username_setting"])
        password = getattr(settings, entry["password_setting"])
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            continue
        db.add(
            User(
                username=username,
                name=entry["name"],
                password_hash=hash_password(password),
                role=entry["role"],
            )
        )
    db.commit()


def _issue_tokens(user: User) -> TokenResponse:
    payload = {"sub": str(user.id), "role": user.role.value}
    return TokenResponse(
        access_token=create_access_token(payload),
        refresh_token=create_refresh_token(payload),
    )


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == request.username).first()
    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is deactivated",
        )
    return _issue_tokens(user)


@router.post("/refresh", response_model=TokenResponse)
def refresh(request: RefreshRequest, db: Session = Depends(get_db)):
    payload = decode_token(request.refresh_token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    return _issue_tokens(user)


@router.get("/me", response_model=UserRead)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user
