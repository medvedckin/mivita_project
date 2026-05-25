from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models.user import User
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
    access_token = create_access_token(
        {"sub": str(user.id), "role": user.role.value}
    )
    refresh_token = create_refresh_token(
        {"sub": str(user.id), "role": user.role.value}
    )
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


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
    access_token = create_access_token(
        {"sub": str(user.id), "role": user.role.value}
    )
    refresh_token = create_refresh_token(
        {"sub": str(user.id), "role": user.role.value}
    )
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.get("/me", response_model=UserRead)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/seed", status_code=status.HTTP_201_CREATED)
def seed_users(db: Session = Depends(get_db)):
    """Seed initial users (admin, partner, cook). Only works if no users exist."""
    existing = db.query(User).count()
    if existing > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Users already exist",
        )
    users = [
        User(
            username="admin",
            password_hash=hash_password("admin123"),
            role="admin",
        ),
        User(
            username="partner",
            password_hash=hash_password("partner123"),
            role="partner",
        ),
        User(
            username="cook",
            password_hash=hash_password("cook123"),
            role="cook",
        ),
    ]
    db.add_all(users)
    db.commit()
    return {"message": "Users created", "users": ["admin", "partner", "cook"]}
