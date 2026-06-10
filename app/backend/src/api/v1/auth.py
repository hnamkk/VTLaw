"""Authentication endpoints."""

import re
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import require_user
from src.auth.security import create_access_token, hash_password, verify_password
from src.db.session import get_session
from src.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])

_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_PASSWORD_LETTER_PATTERN = re.compile(r"[A-Za-z]")
_PASSWORD_DIGIT_PATTERN = re.compile(r"\d")


def _normalize_email(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized:
        raise ValueError("Vui lòng nhập email.")
    if len(normalized) < 3 or len(normalized) > 100:
        raise ValueError("Email phải có từ 3 đến 100 ký tự.")
    if " " in normalized:
        raise ValueError("Email không được chứa khoảng trắng.")
    if normalized.count("@") != 1 or not _EMAIL_PATTERN.fullmatch(normalized):
        raise ValueError("Email không hợp lệ.")
    local_part, domain_part = normalized.split("@", 1)
    if not local_part or not domain_part:
        raise ValueError("Email không hợp lệ.")
    if ".." in normalized or domain_part.startswith(".") or domain_part.endswith("."):
        raise ValueError("Email không hợp lệ.")
    return normalized


def _normalize_username(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise ValueError("Vui lòng nhập họ và tên.")
    if len(normalized) < 2 or len(normalized) > 50:
        raise ValueError("Họ và tên phải có từ 2 đến 50 ký tự.")
    letter_count = sum(1 for char in normalized if char.isalpha())
    if letter_count < 2:
        raise ValueError("Họ và tên phải chứa ít nhất 2 chữ cái.")
    return normalized


def _validate_password_strength(value: str, *, field_label: str) -> str:
    if not value:
        raise ValueError(f"Vui lòng nhập {field_label}.")
    if len(value) < 8 or len(value) > 128:
        raise ValueError(f"{field_label.capitalize()} phải có từ 8 đến 128 ký tự.")
    if any(char.isspace() for char in value):
        raise ValueError(f"{field_label.capitalize()} không được chứa khoảng trắng.")
    if _PASSWORD_LETTER_PATTERN.search(value) is None:
        raise ValueError(f"{field_label.capitalize()} phải có ít nhất 1 chữ cái.")
    if _PASSWORD_DIGIT_PATTERN.search(value) is None:
        raise ValueError(f"{field_label.capitalize()} phải có ít nhất 1 chữ số.")
    return value


class UserPublic(BaseModel):
    user_id: str
    email: str
    username: str | None = None
    role: str
    is_active: bool


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


class RegisterRequest(BaseModel):
    email: str
    password: str
    confirm_password: str
    username: str | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _normalize_email(value)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _validate_password_strength(value, field_label="mật khẩu")

    @field_validator("confirm_password")
    @classmethod
    def validate_confirm_password(cls, value: str) -> str:
        if not value:
            raise ValueError("Vui lòng nhập xác nhận mật khẩu.")
        return value

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str | None) -> str | None:
        return _normalize_username(value)

    @model_validator(mode="after")
    def validate_passwords_match(self) -> "RegisterRequest":
        if self.password != self.confirm_password:
            raise ValueError("Xác nhận mật khẩu chưa khớp.")
        return self


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _normalize_email(value)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not value:
            raise ValueError("Vui lòng nhập mật khẩu.")
        if len(value) > 128:
            raise ValueError("Mật khẩu không được vượt quá 128 ký tự.")
        return value


class UpdateProfileRequest(BaseModel):
    email: str
    username: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _normalize_email(value)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        normalized = _normalize_username(value)
        assert normalized is not None
        return normalized


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str

    @field_validator("current_password")
    @classmethod
    def validate_current_password(cls, value: str) -> str:
        if not value:
            raise ValueError("Vui lòng nhập mật khẩu hiện tại.")
        if len(value) > 128:
            raise ValueError("Mật khẩu hiện tại không được vượt quá 128 ký tự.")
        return value

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        return _validate_password_strength(value, field_label="mật khẩu mới")

    @field_validator("confirm_password")
    @classmethod
    def validate_confirm_password(cls, value: str) -> str:
        if not value:
            raise ValueError("Vui lòng nhập xác nhận mật khẩu mới.")
        return value

    @model_validator(mode="after")
    def validate_passwords(self) -> "ChangePasswordRequest":
        if self.current_password == self.new_password:
            raise ValueError("Mật khẩu mới phải khác mật khẩu hiện tại.")
        if self.new_password != self.confirm_password:
            raise ValueError("Xác nhận mật khẩu mới chưa khớp.")
        return self


def _public_user(user: User) -> UserPublic:
    return UserPublic(
        user_id=user.user_id,
        email=user.email,
        username=user.username,
        role=user.role,
        is_active=user.is_active,
    )


def _auth_response(user: User) -> AuthResponse:
    return AuthResponse(access_token=create_access_token(user.user_id, user.role), user=_public_user(user))


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db_session: AsyncSession = Depends(get_session)):
    email = payload.email
    existing = await db_session.execute(select(User).where(func.lower(User.email) == email.lower()))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email đã được sử dụng.")

    if payload.username:
        username_result = await db_session.execute(
            select(User).where(func.lower(User.username) == payload.username.lower())
        )
        if username_result.scalar_one_or_none() is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Họ và tên đã được sử dụng.")

    user = User(
        email=email,
        username=payload.username,
        password_hash=hash_password(payload.password),
        role="USER",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return _auth_response(user)


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest, db_session: AsyncSession = Depends(get_session)):
    result = await db_session.execute(select(User).where(func.lower(User.email) == payload.email.lower()))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email hoặc mật khẩu không đúng.")

    user.last_login_at = datetime.now(UTC)
    await db_session.commit()
    await db_session.refresh(user)
    return _auth_response(user)


@router.get("/me", response_model=UserPublic)
async def me(user: User = Depends(require_user)):
    return _public_user(user)


@router.patch("/me", response_model=UserPublic)
async def update_me(
    payload: UpdateProfileRequest,
    user: User = Depends(require_user),
    db_session: AsyncSession = Depends(get_session),
):
    email_result = await db_session.execute(select(User).where(func.lower(User.email) == payload.email.lower()))
    email_owner = email_result.scalar_one_or_none()
    if email_owner is not None and email_owner.user_id != user.user_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email đã được sử dụng.")

    username_result = await db_session.execute(
        select(User).where(func.lower(User.username) == payload.username.lower())
    )
    username_owner = username_result.scalar_one_or_none()
    if username_owner is not None and username_owner.user_id != user.user_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Họ và tên đã được sử dụng.")

    user.email = payload.email
    user.username = payload.username
    await db_session.commit()
    await db_session.refresh(user)
    return _public_user(user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: ChangePasswordRequest,
    user: User = Depends(require_user),
    db_session: AsyncSession = Depends(get_session),
):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mật khẩu hiện tại không đúng.")

    user.password_hash = hash_password(payload.new_password)
    await db_session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout():
    return Response(status_code=status.HTTP_204_NO_CONTENT)
