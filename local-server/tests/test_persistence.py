"""Tests for persistent SpaceRepository and native WiFi scanning."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.repositories.space_repository import SpaceRepository
from app.services.wifi_integration_service import (
    WiFiIntegrationService,
    _native_wifi_scan,
    _scan_nmcli,
)


# ── SpaceRepository persistence ──────────────────────────────────────


class TestSpaceRepositoryPersistence:
    """Verify that spaces are persisted to and loaded from a JSON file."""

    def _tmp_path(self, tmp_path: Path) -> Path:
        return tmp_path / "spaces.json"

    def test_create_persists_to_file(self, tmp_path):
        path = self._tmp_path(tmp_path)
        repo = SpaceRepository(path=path)
        repo.create(user_id=1, name="Cocina", space_type="kitchen", wifi_metadata={"source": "test"})

        assert path.exists(), "JSON file should be created after first space"
        raw = json.loads(path.read_text())
        assert "spaces" in raw
        assert len(raw["spaces"]) == 1

    def test_load_from_existing_file(self, tmp_path):
        path = self._tmp_path(tmp_path)
        # Create a repo & add data
        repo1 = SpaceRepository(path=path)
        repo1.create(user_id=1, name="Sala", space_type="living_room")
        repo1.create(user_id=1, name="Oficina", space_type="office")

        # Create a NEW repo instance pointing at the same file
        repo2 = SpaceRepository(path=path)
        spaces = repo2.list_by_user(1)
        assert len(spaces) == 2
        names = {s.name for s in spaces}
        assert names == {"Sala", "Oficina"}

    def test_delete_persists(self, tmp_path):
        path = self._tmp_path(tmp_path)
        repo = SpaceRepository(path=path)
        space = repo.create(user_id=1, name="Temp", space_type="room")
        repo.delete(space.id)

        # Reload from file
        repo2 = SpaceRepository(path=path)
        assert repo2.get_by_id(space.id) is None

    def test_next_id_survives_reload(self, tmp_path):
        path = self._tmp_path(tmp_path)
        repo = SpaceRepository(path=path)
        s1 = repo.create(user_id=1, name="A", space_type="room")

        repo2 = SpaceRepository(path=path)
        s2 = repo2.create(user_id=1, name="B", space_type="room")
        assert s2.id > s1.id, "IDs should be monotonically increasing after reload"

    def test_empty_file_starts_fresh(self, tmp_path):
        path = self._tmp_path(tmp_path)
        repo = SpaceRepository(path=path)
        assert repo.list_by_user(1) == []

    def test_wifi_metadata_roundtrip(self, tmp_path):
        path = self._tmp_path(tmp_path)
        wifi = {
            "networks_detected": 5,
            "readings": [{"bssid": "AA:BB", "ssid": "Net", "rssi": -50, "channel": 6}],
            "source": "native_linux",
        }
        repo = SpaceRepository(path=path)
        space = repo.create(user_id=1, name="X", space_type="room", wifi_metadata=wifi)

        repo2 = SpaceRepository(path=path)
        loaded = repo2.get_by_id(space.id)
        assert loaded is not None
        assert loaded.wifi_metadata["networks_detected"] == 5
        assert loaded.wifi_metadata["source"] == "native_linux"
        assert len(loaded.wifi_metadata["readings"]) == 1


# ── Native WiFi scanning ─────────────────────────────────────────────


class TestNativeWifiScanning:
    """Test the native Linux scanner fallback logic."""

    MOCK_NMCLI_OUTPUT = (
        r"AA\:BB\:CC\:DD\:EE\:01:HomeNetwork:75:6" + "\n"
        r"AA\:BB\:CC\:DD\:EE\:02:OfficeNet:40:11" + "\n"
    )

    def test_scan_nmcli_parses_output(self):
        """When nmcli is available and returns data, it should be parsed."""
        fake_result = type("R", (), {"returncode": 0, "stdout": self.MOCK_NMCLI_OUTPUT, "stderr": ""})()
        with (
            patch("app.services.wifi_integration_service.shutil.which", return_value="/usr/bin/nmcli"),
            patch("app.services.wifi_integration_service.subprocess.run", return_value=fake_result),
        ):
            readings = _scan_nmcli()

        assert readings is not None
        assert len(readings) == 2
        assert readings[0]["bssid"] == "AA:BB:CC:DD:EE:01"
        assert readings[0]["ssid"] == "HomeNetwork"
        assert readings[0]["channel"] == 6
        # signal 75% → dBm = -100 + 75*0.7 = -47.5 → -47
        assert readings[0]["rssi"] == -47

    def test_native_scan_returns_none_when_no_tools(self):
        """When neither nmcli nor iwlist are available, return None."""
        with patch("app.services.wifi_integration_service.shutil.which", return_value=None):
            result = _native_wifi_scan()
        assert result is None

    def test_service_uses_native_before_mock(self):
        """WiFiIntegrationService should try native scan before falling back to mock."""
        native_data = {
            "networks_detected": 2,
            "readings": [{"bssid": "X", "ssid": "Y", "rssi": -50, "channel": 1}],
            "source": "native_linux",
        }
        service = WiFiIntegrationService()
        # Force scanner to None (no wifipos)
        service._scanner = None
        with patch("app.services.wifi_integration_service._native_wifi_scan", return_value=native_data):
            result = service.scan_current_environment()
        assert result["source"] == "native_linux"

    def test_service_falls_back_to_mock_when_native_fails(self):
        """If native scan also fails, mock data is returned."""
        service = WiFiIntegrationService()
        service._scanner = None
        with patch("app.services.wifi_integration_service._native_wifi_scan", return_value=None):
            result = service.scan_current_environment()
        assert result["source"] == "mock"


# ── Fingerprint saving & auto-training ───────────────────────────────


class TestFingerprintAndTraining:
    """Test that space registration saves fingerprints and trains the model."""

    def _make_service(self) -> WiFiIntegrationService:
        """Create a WiFiIntegrationService backed by an in-memory database."""
        service = WiFiIntegrationService(db_path=":memory:")
        service._scanner = None  # no real WiFi hardware in CI
        return service

    def _mock_readings(self, n: int = 3) -> list[dict]:
        """Return *n* distinct fake WiFi readings."""
        return [
            {
                "bssid": f"AA:BB:CC:DD:EE:{i:02X}",
                "ssid": f"Network_{i}",
                "rssi": -40 - i * 5,
                "channel": 6 + i,
            }
            for i in range(n)
        ]

    def test_save_fingerprint_stores_to_db(self):
        """save_fingerprint() should persist readings in the wifipos DB."""
        service = self._make_service()
        metadata = {"networks_detected": 3, "readings": self._mock_readings(), "source": "mock"}

        ok = service.save_fingerprint("Cocina", metadata)

        assert ok is True
        counts = service._db.get_fingerprint_count_by_location()
        assert counts == {"Cocina": 1}

    def test_save_fingerprint_no_readings(self):
        """save_fingerprint() with empty readings returns False."""
        service = self._make_service()
        ok = service.save_fingerprint("Empty", {"networks_detected": 0, "readings": []})
        assert ok is False

    def test_save_fingerprint_no_db(self):
        """save_fingerprint() returns False when DB is not available."""
        service = self._make_service()
        service._db = None
        ok = service.save_fingerprint("Room", {"readings": self._mock_readings()})
        assert ok is False

    def test_try_train_skips_with_one_location(self):
        """Training should be skipped if only 1 location has fingerprints."""
        service = self._make_service()
        for _ in range(5):
            service.save_fingerprint("Cocina", {"readings": self._mock_readings()})

        result = service.try_train_model()
        assert result is None  # need ≥2 locations

    def test_try_train_skips_with_few_fingerprints(self):
        """Training should be skipped if a location has <3 fingerprints."""
        service = self._make_service()
        for _ in range(5):
            service.save_fingerprint("Cocina", {"readings": self._mock_readings()})
        service.save_fingerprint("Sala", {"readings": self._mock_readings()})  # only 1

        result = service.try_train_model()
        assert result is None  # Sala has < 3

    def test_try_train_succeeds_with_enough_data(self):
        """Training should succeed with ≥2 locations and ≥3 fingerprints each."""
        service = self._make_service()
        # Cocina: 4 fingerprints with distinct signals
        for i in range(4):
            service.save_fingerprint("Cocina", {
                "readings": [
                    {"bssid": "AA:BB:CC:DD:EE:01", "ssid": "Net1", "rssi": -40 + i, "channel": 6},
                    {"bssid": "AA:BB:CC:DD:EE:02", "ssid": "Net2", "rssi": -60 + i, "channel": 11},
                ],
            })
        # Sala: 4 fingerprints with different signal pattern
        for i in range(4):
            service.save_fingerprint("Sala", {
                "readings": [
                    {"bssid": "AA:BB:CC:DD:EE:01", "ssid": "Net1", "rssi": -70 + i, "channel": 6},
                    {"bssid": "AA:BB:CC:DD:EE:02", "ssid": "Net2", "rssi": -35 + i, "channel": 11},
                ],
            })

        result = service.try_train_model()
        assert result is not None
        assert "accuracy" in result
        assert "classifier" in result
        assert set(result["locations"]) == {"Cocina", "Sala"}

    def test_try_train_no_db(self):
        """try_train_model() returns None when DB is not available."""
        service = self._make_service()
        service._db = None
        assert service.try_train_model() is None
