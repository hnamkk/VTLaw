"""ADMIN user-account management endpoints."""

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.auth import _normalize_email, _normalize_username, _validate_password_strength
from src.auth.dependencies import require_admin
from src.auth.security import hash_password
from src.db.session import get_session
from src.models.user import User

router = APIRouter(
    prefix="/admin/users",
    tags=["admin-users"],
    dependencies=[Depends(require_admin)],
)


class AdminUserOut(BaseModel):
    user_id: str
    email: str
    username: str | None = None
    role: Literal["USER", "ADMIN"]
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None


class AdminUserListResponse(BaseModel):
    items: list[AdminUserOut]
    total: int
    page: int
    page_size: int


class AdminUserCreateRequest(BaseModel):
    username: str
    email: str
    password: str
    confirm_password: str
    role: Literal["USER", "ADMIN"] = "USER"

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        normalized = _normalize_username(value)
        assert normalized is not None
        return normalized

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _normalize_email(value)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _validate_password_strength(value, field_label="mật khẩu")

    @model_validator(mode="after")
    def validate_password_confirmation(self) -> "AdminUserCreateRequest":
        if self.password != self.confirm_password:
            raise ValueError("Xác nhận mật khẩu chưa khớp.")
        return self


class AdminUserUpdateRequest(BaseModel):
    username: str | None = None
    email: str | None = None
    role: Literal["USER", "ADMIN"] | None = None
    is_active: bool | None = None

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str | None) -> str | None:
        return _normalize_username(value)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        return _normalize_email(value) if value is not None else None

    @model_validator(mode="after")
    def require_change(self) -> "AdminUserUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("Cần chọn ít nhất một thông tin để cập nhật.")
        return self


class AdminPasswordResetRequest(BaseModel):
    new_password: str
    confirm_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _validate_password_strength(value, field_label="mật khẩu mới")

    @model_validator(mode="after")
    def validate_confirmation(self) -> "AdminPasswordResetRequest":
        if self.new_password != self.confirm_password:
            raise ValueError("Xác nhận mật khẩu mới chưa khớp.")
        return self


def _user_out(user: User) -> AdminUserOut:
    return AdminUserOut(
        user_id=user.user_id,
        email=user.email,
        username=user.username,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


def _filters(*, q: str | None, role: str | None, is_active: bool | None) -> list:
    filters = []
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        filters.append(or_(User.username.ilike(pattern), User.email.ilike(pattern)))
    if role:
        filters.append(User.role == role)
    if is_active is not None:
        filters.append(User.is_active == is_active)
    return filters


async def _get_user_or_404(db_session: AsyncSession, user_id: UUID) -> User:
    user = await db_session.get(User, str(user_id))
    if user is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản.")
    return user


async def _ensure_unique_identity(
    db_session: AsyncSession,
    *,
    email: str | None,
    username: str | None,
    exclude_user_id: str | None = None,
) -> None:
    if email is not None:
        statement = select(User.user_id).where(func.lower(User.email) == email.lower())
        if exclude_user_id:
            statement = statement.where(User.user_id != exclude_user_id)
        if await db_session.scalar(statement) is not None:
            raise HTTPException(status_code=409, detail="Email đã được sử dụng.")
    if username is not None:
        statement = select(User.user_id).where(func.lower(User.username) == username.lower())
        if exclude_user_id:
            statement = statement.where(User.user_id != exclude_user_id)
        if await db_session.scalar(statement) is not None:
            raise HTTPException(status_code=409, detail="Họ và tên đã được sử dụng.")


async def _guard_admin_access(
    db_session: AsyncSession,
    *,
    target: User,
    actor: User,
    next_role: str,
    next_active: bool,
) -> None:
    if target.user_id == actor.user_id and (next_role != "ADMIN" or not next_active):
        raise HTTPException(
            status_code=409,
            detail="Bạn không thể tự hạ quyền hoặc khóa tài khoản của mình.",
        )
    if target.role == "ADMIN" and target.is_active and (
        next_role != "ADMIN" or not next_active
    ):
        other_active_admins = await db_session.scalar(
            select(func.count())
            .select_from(User)
            .where(
                User.role == "ADMIN",
                User.is_active.is_(True),
                User.user_id != target.user_id,
            )
        )
        if not other_active_admins:
            raise HTTPException(
                status_code=409,
                detail="Hệ thống phải còn ít nhất một quản trị viên đang hoạt động.",
            )


@router.get("", response_model=AdminUserListResponse)
async def list_admin_users(
    q: str | None = Query(None, max_length=100),
    role: Literal["USER", "ADMIN"] | None = Query(None),
    is_active: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db_session: AsyncSession = Depends(get_session),
):
    filters = _filters(q=q, role=role, is_active=is_active)
    total = int(
        await db_session.scalar(select(func.count()).select_from(User).where(*filters)) or 0
    )
    users = list(
        (
            await db_session.scalars(
                select(User)
                .where(*filters)
                .order_by(User.created_at.desc(), User.user_id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    return AdminUserListResponse(
        items=[_user_out(user) for user in users],
        total=total,
        page=page,
        page_size=page_size,
    )


_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@")
_CSV_LEADING_CONTROL_CHARS = " \t\r\n\v\f"


def _safe_csv_cell(value: str) -> str:
    normalized = str(value).replace("\r", " ").replace("\n", " ").replace("\t", " ")
    if normalized.lstrip(_CSV_LEADING_CONTROL_CHARS).startswith(_CSV_FORMULA_PREFIXES):
        return f"'{normalized}"
    return normalized


@router.get("/export")
async def export_admin_users(
    q: str | None = Query(None, max_length=100),
    role: Literal["USER", "ADMIN"] | None = Query(None),
    is_active: bool | None = Query(None),
    db_session: AsyncSession = Depends(get_session),
):
    users = list(
        (
            await db_session.scalars(
                select(User)
                .where(*_filters(q=q, role=role, is_active=is_active))
                .order_by(User.created_at.desc(), User.user_id.desc())
            )
        ).all()
    )
    stream = io.StringIO()
    stream.write("\ufeff")
    writer = csv.writer(stream, quoting=csv.QUOTE_ALL)
    writer.writerow(
        ["Họ và tên", "Email", "Vai trò", "Trạng thái", "Ngày tạo", "Đăng nhập gần nhất"]
    )
    for user in users:
        writer.writerow(
            [
                _safe_csv_cell(user.username or ""),
                _safe_csv_cell(user.email),
                user.role,
                "Hoạt động" if user.is_active else "Đã khóa",
                user.created_at.isoformat() if user.created_at else "",
                user.last_login_at.isoformat() if user.last_login_at else "",
            ]
        )
    content = stream.getvalue().encode("utf-8")
    return StreamingResponse(
        iter([content]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="vt-law-users.csv"'},
    )


@router.post("", response_model=AdminUserOut, status_code=status.HTTP_201_CREATED)
async def create_admin_user(
    payload: AdminUserCreateRequest,
    db_session: AsyncSession = Depends(get_session),
):
    await _ensure_unique_identity(
        db_session,
        email=payload.email,
        username=payload.username,
    )
    user = User(
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=True,
    )
    db_session.add(user)
    try:
        await db_session.commit()
    except IntegrityError as exc:
        await db_session.rollback()
        raise HTTPException(status_code=409, detail="Email hoặc họ và tên đã được sử dụng.") from exc
    await db_session.refresh(user)
    return _user_out(user)


@router.patch("/{user_id}", response_model=AdminUserOut)
async def update_admin_user(
    user_id: UUID,
    payload: AdminUserUpdateRequest,
    current_admin: User = Depends(require_admin),
    db_session: AsyncSession = Depends(get_session),
):
    user = await _get_user_or_404(db_session, user_id)
    next_role = payload.role if payload.role is not None else user.role
    next_active = payload.is_active if payload.is_active is not None else user.is_active
    await _guard_admin_access(
        db_session,
        target=user,
        actor=current_admin,
        next_role=next_role,
        next_active=next_active,
    )
    await _ensure_unique_identity(
        db_session,
        email=payload.email,
        username=payload.username,
        exclude_user_id=user.user_id,
    )
    if payload.username is not None:
        user.username = payload.username
    if payload.email is not None:
        user.email = payload.email
    user.role = next_role
    user.is_active = next_active
    try:
        await db_session.commit()
    except IntegrityError as exc:
        await db_session.rollback()
        raise HTTPException(status_code=409, detail="Email hoặc họ và tên đã được sử dụng.") from exc
    await db_session.refresh(user)
    return _user_out(user)


@router.post("/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_admin_user_password(
    user_id: UUID,
    payload: AdminPasswordResetRequest,
    db_session: AsyncSession = Depends(get_session),
):
    user = await _get_user_or_404(db_session, user_id)
    user.password_hash = hash_password(payload.new_password)
    await db_session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_admin_user(
    user_id: UUID,
    current_admin: User = Depends(require_admin),
    db_session: AsyncSession = Depends(get_session),
):
    user = await _get_user_or_404(db_session, user_id)
    await _guard_admin_access(
        db_session,
        target=user,
        actor=current_admin,
        next_role=user.role,
        next_active=False,
    )
    user.is_active = False
    await db_session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
