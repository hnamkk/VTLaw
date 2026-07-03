import bcrypt
import pytest
from pydantic import ValidationError

from src.auth.security import hash_password, verify_password
from src.core.config import Settings


def test_hash_password_accepts_long_password_without_bcrypt_byte_limit():
    password = "Strongpass1" * 8

    password_hash = hash_password(password)

    assert password_hash.startswith("$2")
    assert verify_password(password, password_hash)
    assert not verify_password(f"{password}x", password_hash)


def test_verify_password_rejects_raw_bcrypt_hashes():
    password = "Strongpass1"
    raw_bcrypt_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")

    assert not verify_password(password, raw_bcrypt_hash)


def test_production_requires_non_default_jwt_secret():
    with pytest.raises(ValidationError):
        Settings(APP_ENV="production", JWT_SECRET_KEY="change-me-in-production")
