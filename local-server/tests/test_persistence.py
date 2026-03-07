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
