from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from src.auth.dependencies import require_admin
from src.db.session import get_session
from src.main import app


def _user(
    *,
    user_id="10010010-0100-1001-0010-010010010055",
    username="Nguyễn Văn An",
    email="an@example.test",
    role="USER",
    is_active=True,
):
    return SimpleNamespace(
        user_id=user_id,
        username=username,
        email=email,
        password_hash="hashed:Password1",
        role=role,
        is_active=is_active,
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
        last_login_at=None,
    )


class _ScalarsResult:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class _AdminUserSession:
    def __init__(self, *, scalar_results=None, scalars_results=None, users=None):
        self.scalar_results = list(scalar_results or [])
        self.scalars_results = list(scalars_results or [])
        self.users = dict(users or {})
        self.added = None
        self.commits = 0
        self.rollbacks = 0

    async def scalar(self, _statement):
        return self.scalar_results.pop(0) if self.scalar_results else None

    async def scalars(self, _statement):
        values = self.scalars_results.pop(0) if self.scalars_results else []
        return _ScalarsResult(values)

    async def get(self, _model, user_id):
        return self.users.get(user_id)

    def add(self, value):
        self.added = value

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def refresh(self, value):
        if getattr(value, "user_id", None) is None:
            value.user_id = "30030030-0300-3003-0030-030030030055"
        if getattr(value, "created_at", None) is None:
            value.created_at = datetime(2026, 6, 29, tzinfo=UTC)
        if getattr(value, "last_login_at", None) is None:
            value.last_login_at = None


def _override(session, admin=None):
    async def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[require_admin] = lambda: admin or _user(role="ADMIN")


def _clear_overrides():
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(require_admin, None)


@pytest.fixture(autouse=True)
def fake_hash(monkeypatch):
    monkeypatch.setattr(
        "src.api.v1.admin_users.hash_password",
        lambda value: f"hashed:{value}",
    )


@pytest.mark.asyncio
async def test_admin_user_routes_require_authentication(client):
    response = await client.get("/api/v1/admin/users")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_user_list_returns_real_page_shape(client):
    user = _user()
    session = _AdminUserSession(scalar_results=[1], scalars_results=[[user]])
    _override(session)
    try:
        response = await client.get("/api/v1/admin/users?page=1&page_size=20")
    finally:
        _clear_overrides()

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["email"] == "an@example.test"


@pytest.mark.asyncio
async def test_admin_can_create_normalized_user(client):
    session = _AdminUserSession(scalar_results=[None, None])
    _override(session)
    try:
        response = await client.post(
            "/api/v1/admin/users",
            json={
                "username": "  Nguyễn   Văn   Bình  ",
                "email": " Binh@Example.Test ",
                "password": "Password1",
                "confirm_password": "Password1",
                "role": "USER",
            },
        )
    finally:
        _clear_overrides()

    assert response.status_code == 201
    assert response.json()["username"] == "Nguyễn Văn Bình"
    assert response.json()["email"] == "binh@example.test"
    assert session.added.password_hash == "hashed:Password1"


@pytest.mark.asyncio
async def test_admin_cannot_lock_self(client):
    admin = _user(role="ADMIN")
    session = _AdminUserSession(users={admin.user_id: admin})
    _override(session, admin)
    try:
        response = await client.patch(
            f"/api/v1/admin/users/{admin.user_id}",
            json={"is_active": False},
        )
    finally:
        _clear_overrides()

    assert response.status_code == 409
    assert session.commits == 0


@pytest.mark.asyncio
async def test_last_active_admin_cannot_be_demoted(client):
    actor = _user(
        user_id="20020020-0200-2002-0020-020020020055",
        email="actor@example.test",
        role="ADMIN",
    )
    target = _user(role="ADMIN")
    session = _AdminUserSession(
        scalar_results=[0],
        users={target.user_id: target},
    )
    _override(session, actor)
    try:
        response = await client.patch(
            f"/api/v1/admin/users/{target.user_id}",
            json={"role": "USER"},
        )
    finally:
        _clear_overrides()

    assert response.status_code == 409
    assert session.commits == 0


@pytest.mark.asyncio
async def test_admin_can_lock_regular_user(client):
    actor = _user(role="ADMIN")
    target = _user(
        user_id="20020020-0200-2002-0020-020020020055",
        email="driver@example.test",
    )
    session = _AdminUserSession(users={target.user_id: target})
    _override(session, actor)
    try:
        response = await client.patch(
            f"/api/v1/admin/users/{target.user_id}",
            json={"is_active": False},
        )
    finally:
        _clear_overrides()

    assert response.status_code == 200
    assert response.json()["is_active"] is False
    assert session.commits == 1


@pytest.mark.asyncio
async def test_admin_can_reset_user_password(client):
    target = _user()
    session = _AdminUserSession(users={target.user_id: target})
    _override(session)
    try:
        response = await client.post(
            f"/api/v1/admin/users/{target.user_id}/reset-password",
            json={"new_password": "NewPassword2", "confirm_password": "NewPassword2"},
        )
    finally:
        _clear_overrides()

    assert response.status_code == 204
    assert target.password_hash == "hashed:NewPassword2"
    assert session.commits == 1


@pytest.mark.asyncio
async def test_admin_user_export_escapes_formula_cells(client):
    target = _user(username=" \n=HYPERLINK", email="+safe@example.test")
    session = _AdminUserSession(scalars_results=[[target]])
    _override(session)
    try:
        response = await client.get("/api/v1/admin/users/export")
    finally:
        _clear_overrides()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    content = response.content.decode("utf-8-sig")
    assert "\"'  =HYPERLINK\"" in content
    assert "\"'+safe@example.test\"" in content
