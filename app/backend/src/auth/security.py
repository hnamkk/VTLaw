"""Password hashing and JWT helpers."""

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from jose import JWTError, jwt

from src.core.config import settings

BCRYPT_ROUNDS = 12


def _password_digest(password: str) -> bytes:
    return hashlib.sha256(password.encode("utf-8")).hexdigest().encode("ascii")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_password_digest(password), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode(
        "ascii"
    )


def verify_password(plain_password: str, password_hash: str) -> bool:
    encoded_hash = password_hash.encode("ascii")
    try:
        return bcrypt.checkpw(_password_digest(plain_password), encoded_hash)
    except (UnicodeEncodeError, ValueError):
        return False


def create_access_token(subject: str, role: str, expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload: dict[str, Any] = {"sub": subject, "role": role, "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise ValueError("Invalid access token") from exc
    if not payload.get("sub"):
        raise ValueError("Invalid access token")
    return payload
