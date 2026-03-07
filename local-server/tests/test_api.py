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

    def test_wifipos_diagnostics(self, client):
        """GET /health/wifipos returns detailed wifipos status."""
        resp = client.get("/health/wifipos")
        assert resp.status_code == 200
        body = resp.json()
        assert "wifipos_available" in body
        assert "database_initialized" in body
        assert "scanner_initialized" in body
        assert "dependencies" in body
        # Each dependency should report installed or MISSING
        for dep in ("joblib", "sklearn", "numpy"):
            assert dep in body["dependencies"]


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

    def test_register_space_includes_feedback(self, client):
        """Registration response includes feedback about fingerprints/model."""
        resp = client.post(
            "/spaces",
            json={"name": "FeedbackTest", "space_type": "room", "samples": 1},
        )
        assert resp.status_code == 200
        body = resp.json()
        feedback = body.get("registration_feedback")
        assert feedback is not None
        assert "fingerprints_saved" in feedback
        assert "wifi_source" in feedback
        assert "model_trained" in feedback

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


# ── Model export / import ────────────────────────────────────────────


class TestModelExportImport:
    """Verify model bundle export and import round-trip."""

    def test_export_returns_bundle(self, client):
        """GET /model/export should return a JSON bundle."""
        resp = client.get("/model/export")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert "fingerprints" in data
        assert "exported_at" in data

    def test_import_rejects_invalid_json(self, client):
        """POST /model/import should reject a non-JSON file."""
        resp = client.post(
            "/model/import",
            files={"file": ("bad.wifipos", b"NOT JSON", "application/octet-stream")},
        )
        assert resp.status_code == 400
        assert "error" in resp.json()

    def test_export_import_round_trip(self, client):
        """Export a bundle then import it — fingerprint count should match."""
        # Register a space so there's at least 1 fingerprint
        client.post("/spaces", json={"name": "RT_Cocina", "space_type": "kitchen"})

        # Export
        export_resp = client.get("/model/export")
        assert export_resp.status_code == 200
        bundle = export_resp.json()
        fp_count = len(bundle["fingerprints"])
        assert fp_count >= 1

        # Import
        import json as _json

        bundle_bytes = _json.dumps(bundle).encode()
        import_resp = client.post(
            "/model/import",
            files={"file": ("data.wifipos", bundle_bytes, "application/json")},
        )
        assert import_resp.status_code == 200
        result = import_resp.json()
        assert result["fingerprints_imported"] == fp_count


# ── Consumption ──────────────────────────────────────────────────────


class TestConsumption:
    """Energy consumption tracking endpoints."""

    def test_device_catalog(self, client):
        """GET /consumption/catalog returns available device types."""
        resp = client.get("/consumption/catalog")
        assert resp.status_code == 200
        catalog = resp.json()["devices"]
        assert "tv" in catalog
        assert "lamp" in catalog
        assert catalog["tv"]["watts"] > 0

    def test_register_device(self, client):
        """POST /consumption/devices registers a device to a space."""
        resp = client.post(
            "/consumption/devices",
            json={"space_name": "Cocina", "name": "TV Cocina", "device_type": "tv"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "TV Cocina"
        assert body["space_name"] == "Cocina"
        assert body["is_on"] is False
        assert body["watts"] == 100
        assert "id" in body

    def test_register_device_unknown_type(self, client):
        """POST /consumption/devices rejects unknown device types."""
        resp = client.post(
            "/consumption/devices",
            json={"space_name": "Sala", "name": "Alien", "device_type": "alien"},
        )
        assert resp.status_code == 400

    def test_list_devices(self, client):
        """GET /consumption/devices lists registered devices."""
        client.post(
            "/consumption/devices",
            json={"space_name": "TestList", "name": "Fan1", "device_type": "fan"},
        )
        resp = client.get("/consumption/devices")
        assert resp.status_code == 200
        assert len(resp.json()["devices"]) >= 1

    def test_list_devices_filter_by_space(self, client):
        """GET /consumption/devices?space_name=X filters by space."""
        client.post(
            "/consumption/devices",
            json={"space_name": "FilterSpace", "name": "Lamp1", "device_type": "lamp"},
        )
        resp = client.get("/consumption/devices?space_name=FilterSpace")
        assert resp.status_code == 200
        devices = resp.json()["devices"]
        assert all(d["space_name"] == "FilterSpace" for d in devices)

    def test_toggle_device_on_off(self, client):
        """POST /consumption/event toggles device and records consumption."""
        # Register
        reg = client.post(
            "/consumption/devices",
            json={"space_name": "Toggle", "name": "TV Toggle", "device_type": "tv"},
        )
        device_id = reg.json()["id"]

        # Turn ON
        on_resp = client.post(
            "/consumption/event",
            json={"device_id": device_id, "action": "on"},
        )
        assert on_resp.status_code == 200
        assert on_resp.json()["action"] == "on"

        # Turn OFF
        off_resp = client.post(
            "/consumption/event",
            json={"device_id": device_id, "action": "off"},
        )
        assert off_resp.status_code == 200
        body = off_resp.json()
        assert body["action"] == "off"
        assert "kwh_consumed" in body
        assert "co2_kg" in body

    def test_event_nonexistent_device(self, client):
        """POST /consumption/event 404s for unknown device."""
        resp = client.post(
            "/consumption/event",
            json={"device_id": 99999, "action": "on"},
        )
        assert resp.status_code == 404

    def test_consumption_summary(self, client):
        """GET /consumption/summary returns totals + carbon footprint."""
        resp = client.get("/consumption/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert "total_kwh" in body
        assert "total_co2_kg" in body
        assert "active_watts" in body
        assert "devices" in body
        assert "by_space" in body

    def test_events_list(self, client):
        """GET /consumption/events returns event log."""
        resp = client.get("/consumption/events")
        assert resp.status_code == 200
        assert "events" in resp.json()

    def test_active_devices(self, client):
        """GET /consumption/active returns currently on devices."""
        resp = client.get("/consumption/active")
        assert resp.status_code == 200
        body = resp.json()
        assert "active_count" in body
        assert "total_watts" in body
        assert "devices" in body
