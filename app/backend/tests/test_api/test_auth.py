from types import SimpleNamespace

import pytest

from src.auth.security import create_access_token
from src.db.session import get_session
from src.main import app


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _AuthSession:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.added = None
        self.commits = 0
        self.statements = []

    async def execute(self, _statement):
        self.statements.append(_statement)
        value = self.results.pop(0) if self.results else None
        return _ScalarResult(value)

    def add(self, value):
        self.added = value

    async def commit(self):
        self.commits += 1

    async def refresh(self, value):
        if getattr(value, "user_id", None) is None:
            value.user_id = "10010010-0100-1001-0010-010010010055"
        if getattr(value, "is_active", None) is None:
            value.is_active = True


def _user(
    *,
    user_id="10010010-0100-1001-0010-010010010055",
    email="driver@example.test",
    username="Nguyễn Văn A",
    password="current-password1",
    role="USER",
    is_active=True,
):
    return SimpleNamespace(
        user_id=user_id,
        email=email,
        username=username,
        password_hash=f"hashed:{password}",
        role=role,
        is_active=is_active,
        last_login_at=None,
    )


def _override_session(session):
    async def override():
        yield session

    app.dependency_overrides[get_session] = override


@pytest.fixture(autouse=True)
def fake_password_hashing(monkeypatch):
    monkeypatch.setattr("src.api.v1.auth.hash_password", lambda password: f"hashed:{password}")
    monkeypatch.setattr(
        "src.api.v1.auth.verify_password",
        lambda password, password_hash: password_hash == f"hashed:{password}",
    )


@pytest.mark.asyncio
async def test_register_returns_bearer_token_and_normalized_user(client):
    session = _AuthSession(results=[None, None])
    _override_session(session)
    try:
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": " Driver@Example.Test ",
                "username": "  Nguyễn   Văn   A  ",
                "password": "Strongpass1",
                "confirm_password": "Strongpass1",
            },
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 201
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]
    assert payload["user"]["email"] == "driver@example.test"
    assert payload["user"]["username"] == "Nguyễn Văn A"
    assert payload["user"]["role"] == "USER"
    assert session.added.password_hash == "hashed:Strongpass1"


@pytest.mark.asyncio
async def test_register_rejects_invalid_password_confirmation(client):
    session = _AuthSession(results=[None, None])
    _override_session(session)
    try:
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "driver@example.test",
                "username": "Nguyễn Văn A",
                "password": "Strongpass1",
                "confirm_password": "Strongpass2",
            },
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 422
    assert "Xác nhận mật khẩu chưa khớp." in response.text


@pytest.mark.asyncio
async def test_register_rejects_password_without_digit(client):
    session = _AuthSession(results=[None, None])
    _override_session(session)
    try:
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "driver@example.test",
                "username": "Nguyễn Văn A",
                "password": "Strongpass",
                "confirm_password": "Strongpass",
            },
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 422
    assert "ít nhất 1 chữ số" in response.text


@pytest.mark.asyncio
async def test_register_rejects_invalid_email(client):
    session = _AuthSession(results=[None, None])
    _override_session(session)
    try:
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "driver.example.test",
                "username": "Nguyễn Văn A",
                "password": "Strongpass1",
                "confirm_password": "Strongpass1",
            },
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 422
    assert "Email không hợp lệ." in response.text


@pytest.mark.asyncio
async def test_register_rejects_case_insensitive_username_conflict(client):
    session = _AuthSession(results=[None, _user(username="nguyen van a")])
    _override_session(session)
    try:
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "driver@example.test",
                "username": "Nguyen Van A",
                "password": "Strongpass1",
                "confirm_password": "Strongpass1",
            },
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 409
    assert session.added is None


@pytest.mark.asyncio
async def test_profile_update_requires_authenticated_user(client):
    response = await client.patch(
        "/api/v1/auth/me",
        json={"email": "new@example.test", "username": "Tên mới"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_profile_update_changes_email_and_username(client):
    user = _user()
    session = _AuthSession(results=[user, None, None])
    token = create_access_token(user.user_id, user.role)
    _override_session(session)
    try:
        response = await client.patch(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            json={"email": "new@example.test", "username": "  Tên   mới  "},
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 200
    assert response.json()["email"] == "new@example.test"
    assert response.json()["username"] == "Tên mới"
    assert session.commits == 1


@pytest.mark.asyncio
async def test_profile_update_rejects_short_username(client):
    user = _user()
    session = _AuthSession(results=[user])
    token = create_access_token(user.user_id, user.role)
    _override_session(session)
    try:
        response = await client.patch(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            json={"email": "new@example.test", "username": "A"},
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 422
    assert "Họ và tên phải có từ 2 đến 50 ký tự." in response.text


@pytest.mark.asyncio
async def test_profile_update_rejects_case_insensitive_username_conflict(client):
    user = _user(user_id="10010010-0100-1001-0010-010010010055", username="Nguyen Van A")
    other_user = _user(user_id="20020020-0200-2002-0020-020020020055", username="nguyen van a")
    session = _AuthSession(results=[user, user, other_user])
    token = create_access_token(user.user_id, user.role)
    _override_session(session)
    try:
        response = await client.patch(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            json={"email": "driver@example.test", "username": "Nguyen Van A"},
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 409
    assert session.commits == 0


@pytest.mark.asyncio
async def test_change_password_verifies_current_password(client):
    user = _user(password="old-password1")
    session = _AuthSession(results=[user])
    token = create_access_token(user.user_id, user.role)
    _override_session(session)
    try:
        response = await client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "current_password": "old-password1",
                "new_password": "new-password1",
                "confirm_password": "new-password1",
            },
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 204
    assert user.password_hash == "hashed:new-password1"


@pytest.mark.asyncio
async def test_change_password_rejects_mismatched_confirmation(client):
    user = _user(password="old-password1")
    session = _AuthSession(results=[user])
    token = create_access_token(user.user_id, user.role)
    _override_session(session)
    try:
        response = await client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "current_password": "old-password1",
                "new_password": "new-password1",
                "confirm_password": "new-password2",
            },
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 422
    assert "Xác nhận mật khẩu mới chưa khớp." in response.text


@pytest.mark.asyncio
async def test_user_token_cannot_call_admin_endpoint(client):
    user = _user(role="USER")
    session = _AuthSession(results=[user])
    token = create_access_token(user.user_id, user.role)
    _override_session(session)
    try:
        response = await client.get(
            "/api/v1/admin/legal-kb/revisions?page=1&page_size=1",
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_inactive_user_token_is_rejected(client):
    user = _user(is_active=False)
    session = _AuthSession(results=[user])
    token = create_access_token(user.user_id, user.role)
    _override_session(session)
    try:
        response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 401
