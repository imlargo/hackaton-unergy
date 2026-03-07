"""Tests for the local server API endpoints."""

import uuid

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def registered_user(client):
    """Register a user with a unique email and return (response_data, token)."""
    uid = uuid.uuid4().hex[:8]
    resp = client.post(
        "/auth/register",
        json={
            "username": f"testuser_{uid}",
            "email": f"test_{uid}@example.com",
            "password": "secret123",
        },
    )
    assert resp.status_code == 200, f"Registration failed: {resp.json()}"
    data = resp.json()
    token = data["tokens"]["access_token"]
    return data, token


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Health ────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_check(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "running"
        assert "version" in body


# ── Auth ──────────────────────────────────────────────────────────────

class TestAuth:
    def test_register_success(self, client):
        resp = client.post(
            "/auth/register",
            json={
                "username": "alice",
                "email": "alice@example.com",
                "password": "pass123",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["user"]["email"] == "alice@example.com"
        assert body["user"]["username"] == "alice"
        assert "access_token" in body["tokens"]
        assert "refresh_token" in body["tokens"]
        assert "expires_at" in body["tokens"]

    def test_register_duplicate_email(self, client):
        uid = uuid.uuid4().hex[:8]
        email = f"dup_{uid}@example.com"
        client.post(
            "/auth/register",
            json={
                "username": f"bob_{uid}",
                "email": email,
                "password": "pass",
            },
        )
        resp = client.post(
            "/auth/register",
            json={
                "username": f"bob2_{uid}",
                "email": email,
                "password": "pass",
            },
        )
        assert resp.status_code == 409

    def test_register_duplicate_username(self, client):
        uid = uuid.uuid4().hex[:8]
        username = f"dupuser_{uid}"
        client.post(
            "/auth/register",
            json={
                "username": username,
                "email": f"a_{uid}@example.com",
                "password": "pass",
            },
        )
        resp = client.post(
            "/auth/register",
            json={
                "username": username,
                "email": f"b_{uid}@example.com",
                "password": "pass",
            },
        )
        assert resp.status_code == 409

    def test_login_success(self, client, registered_user):
        data, _ = registered_user
        email = data["user"]["email"]
        resp = client.post(
            "/auth/login",
            json={"email": email, "password": "secret123"},
        )
        assert resp.status_code == 200
        assert resp.json()["user"]["email"] == email

    def test_login_wrong_password(self, client, registered_user):
        data, _ = registered_user
        resp = client.post(
            "/auth/login",
            json={"email": data["user"]["email"], "password": "wrong"},
        )
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client):
        resp = client.post(
            "/auth/login",
            json={"email": "nobody@example.com", "password": "x"},
        )
        assert resp.status_code == 401

    def test_get_me(self, client, registered_user):
        data, token = registered_user
        resp = client.get("/auth/me", headers=auth_header(token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == data["user"]["email"]

    def test_get_me_no_token(self, client):
        resp = client.get("/auth/me")
        assert resp.status_code in (401, 403)

    def test_get_me_invalid_token(self, client):
        resp = client.get("/auth/me", headers=auth_header("bad.token.here"))
        assert resp.status_code == 401


# ── Instructions ──────────────────────────────────────────────────────

class TestInstructions:
    def test_register_space_instructions(self, client):
        resp = client.get("/instructions/register-space")
        assert resp.status_code == 200
        body = resp.json()
        assert "steps" in body
        assert len(body["steps"]) >= 3

    def test_wifi_status(self, client):
        resp = client.get("/instructions/wifi-status")
        assert resp.status_code == 200
        body = resp.json()
        assert "wifi_available" in body
        assert "networks_detected" in body


# ── Spaces ────────────────────────────────────────────────────────────

class TestSpaces:
    def test_register_space(self, client):
        resp = client.post(
            "/spaces",
            json={"name": "Cocina", "space_type": "kitchen"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Cocina"
        assert body["space_type"] == "kitchen"
        assert "wifi_metadata" in body
        assert body["wifi_metadata"]["networks_detected"] >= 1

    def test_list_spaces(self, client):
        # Register two spaces
        client.post(
            "/spaces",
            json={"name": "Sala", "space_type": "living_room"},
        )
        client.post(
            "/spaces",
            json={"name": "Oficina", "space_type": "office"},
        )
        resp = client.get("/spaces")
        assert resp.status_code == 200
        spaces = resp.json()
        assert len(spaces) >= 2
        names = {s["name"] for s in spaces}
        assert "Sala" in names
        assert "Oficina" in names

    def test_get_space_by_id(self, client):
        create_resp = client.post(
            "/spaces",
            json={"name": "Garaje", "space_type": "garage"},
        )
        space_id = create_resp.json()["id"]
        resp = client.get(f"/spaces/{space_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Garaje"

    def test_get_nonexistent_space(self, client):
        resp = client.get("/spaces/999")
        assert resp.status_code == 404

    def test_spaces_no_auth_required(self, client):
        """Spaces endpoints work without any authentication."""
        resp = client.get("/spaces")
        assert resp.status_code == 200
        resp = client.post(
            "/spaces",
            json={"name": "Test", "space_type": "room"},
        )
        assert resp.status_code == 200
