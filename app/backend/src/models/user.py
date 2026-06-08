"""User accounts for authentication and role-based authorization."""

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('USER', 'ADMIN')", name="ck_users_role"),
        Index("idx_users_email", "email"),
        Index("idx_users_role", "role"),
        Index("idx_users_is_active", "is_active"),
    )

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    email: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    username: Mapped[str | None] = mapped_column(String(50), nullable=True, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False, server_default="USER")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)


Index("uq_users_email_lower", func.lower(User.email), unique=True)
Index(
    "uq_users_username_lower",
    func.lower(User.username),
    unique=True,
    postgresql_where=User.username.is_not(None),
)
