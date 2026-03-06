"""Tests for the storage layer."""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from wifipos.storage.database import Database


class TestDatabase:
    """Tests for the SQLite database storage layer."""

    def _make_db(self) -> Database:
        """Create an in-memory database for testing."""
        return Database(":memory:")

    def test_create_database(self) -> None:
        db = self._make_db()
        assert db is not None
        db.close()

    def test_save_and_get_fingerprint(self) -> None:
        db = self._make_db()
        raw_data = [
            {"bssid": "AA:BB:CC:DD:EE:01", "ssid": "Test", "rssi": -50, "channel": 6},
            {"bssid": "AA:BB:CC:DD:EE:02", "ssid": "Test2", "rssi": -60, "channel": 11},
        ]
        fp_id = db.save_fingerprint("office", raw_data)
        assert fp_id is not None
        assert isinstance(fp_id, int)

        fingerprints = db.get_all_fingerprints()
        assert len(fingerprints) == 1
        assert fingerprints[0]["location"] == "office"
        assert len(fingerprints[0]["raw_data"]) == 2
        db.close()

    def test_save_fingerprint_with_timestamp(self) -> None:
        db = self._make_db()
        ts = datetime(2024, 6, 15, 10, 30, 0)
        raw_data = [{"bssid": "AA:BB:CC:DD:EE:01", "rssi": -50}]
        db.save_fingerprint("office", raw_data, timestamp=ts)

        fingerprints = db.get_all_fingerprints()
        assert fingerprints[0]["timestamp"] == "2024-06-15T10:30:00"
        db.close()

    def test_get_fingerprints_by_location(self) -> None:
        db = self._make_db()
        raw_data = [{"bssid": "AA:BB:CC:DD:EE:01", "rssi": -50}]
        db.save_fingerprint("office", raw_data)
        db.save_fingerprint("kitchen", raw_data)
        db.save_fingerprint("office", raw_data)

        office_fps = db.get_fingerprints_by_location("office")
        assert len(office_fps) == 2
        assert all(fp["location"] == "office" for fp in office_fps)

        kitchen_fps = db.get_fingerprints_by_location("kitchen")
        assert len(kitchen_fps) == 1
        db.close()

    def test_get_locations(self) -> None:
        db = self._make_db()
        raw_data = [{"bssid": "AA:BB:CC:DD:EE:01", "rssi": -50}]
        db.save_fingerprint("office", raw_data)
        db.save_fingerprint("kitchen", raw_data)
        db.save_fingerprint("bedroom", raw_data)

        locations = db.get_locations()
        assert locations == ["bedroom", "kitchen", "office"]
        db.close()

    def test_get_fingerprint_count_by_location(self) -> None:
        db = self._make_db()
        raw_data = [{"bssid": "AA:BB:CC:DD:EE:01", "rssi": -50}]
        db.save_fingerprint("office", raw_data)
        db.save_fingerprint("office", raw_data)
        db.save_fingerprint("kitchen", raw_data)

        counts = db.get_fingerprint_count_by_location()
        assert counts == {"kitchen": 1, "office": 2}
        db.close()

    def test_delete_location(self) -> None:
        db = self._make_db()
        raw_data = [{"bssid": "AA:BB:CC:DD:EE:01", "rssi": -50}]
        db.save_fingerprint("office", raw_data)
        db.save_fingerprint("office", raw_data)
        db.save_fingerprint("kitchen", raw_data)

        deleted = db.delete_location("office")
        assert deleted == 2

        locations = db.get_locations()
        assert locations == ["kitchen"]
        db.close()

    def test_delete_nonexistent_location(self) -> None:
        db = self._make_db()
        deleted = db.delete_location("nowhere")
        assert deleted == 0
        db.close()

    def test_save_and_load_model(self) -> None:
        db = self._make_db()
        model_blob = b"fake_model_data_bytes"
        metadata = {"accuracy": 0.95, "locations": ["office", "kitchen"]}

        model_id = db.save_model(model_blob, metadata)
        assert model_id is not None

        model = db.load_latest_model()
        assert model is not None
        assert model["model_blob"] == model_blob
        assert model["metadata"]["accuracy"] == 0.95
        assert model["metadata"]["locations"] == ["office", "kitchen"]
        db.close()

    def test_load_latest_model_returns_most_recent(self) -> None:
        db = self._make_db()
        db.save_model(b"model_v1", {"version": 1})
        db.save_model(b"model_v2", {"version": 2})

        model = db.load_latest_model()
        assert model is not None
        assert model["metadata"]["version"] == 2
        assert model["model_blob"] == b"model_v2"
        db.close()

    def test_load_latest_model_none_when_empty(self) -> None:
        db = self._make_db()
        assert db.load_latest_model() is None
        db.close()

    def test_reset(self) -> None:
        db = self._make_db()
        raw_data = [{"bssid": "AA:BB:CC:DD:EE:01", "rssi": -50}]
        db.save_fingerprint("office", raw_data)
        db.save_model(b"model_data", {"version": 1})

        db.reset()

        assert db.get_all_fingerprints() == []
        assert db.load_latest_model() is None
        assert db.get_locations() == []
        db.close()

    def test_context_manager(self) -> None:
        with Database(":memory:") as db:
            raw_data = [{"bssid": "AA:BB:CC:DD:EE:01", "rssi": -50}]
            db.save_fingerprint("office", raw_data)
            assert len(db.get_all_fingerprints()) == 1

    def test_empty_database(self) -> None:
        db = self._make_db()
        assert db.get_all_fingerprints() == []
        assert db.get_locations() == []
        assert db.get_fingerprint_count_by_location() == {}
        db.close()
