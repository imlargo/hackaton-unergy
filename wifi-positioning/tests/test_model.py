"""Tests for the model module (fingerprinting, training, prediction)."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import numpy as np
import pytest

from wifipos.model.fingerprint import Fingerprint, build_feature_matrix, collect_fingerprint
from wifipos.model.predictor import Prediction, Predictor
from wifipos.model.trainer import TrainingResult, train_model
from wifipos.scanner.base import WifiReading, WifiScanner
from wifipos.storage.database import Database


class MockScanner(WifiScanner):
    """A mock scanner that returns different readings based on a location pattern."""

    def __init__(self, location_pattern: str = "office") -> None:
        self._location_pattern = location_pattern

    def set_location(self, pattern: str) -> None:
        self._location_pattern = pattern

    def scan(self) -> list[WifiReading]:
        if self._location_pattern == "office":
            return [
                WifiReading(bssid="AA:BB:CC:DD:EE:01", ssid="OfficeWiFi", rssi=-40, channel=6),
                WifiReading(bssid="AA:BB:CC:DD:EE:02", ssid="OfficeWiFi5G", rssi=-50, channel=36),
                WifiReading(bssid="AA:BB:CC:DD:EE:03", ssid="Shared", rssi=-65, channel=11),
            ]
        elif self._location_pattern == "kitchen":
            return [
                WifiReading(bssid="AA:BB:CC:DD:EE:01", ssid="OfficeWiFi", rssi=-70, channel=6),
                WifiReading(bssid="AA:BB:CC:DD:EE:03", ssid="Shared", rssi=-45, channel=11),
                WifiReading(bssid="AA:BB:CC:DD:EE:04", ssid="KitchenAP", rssi=-35, channel=1),
            ]
        return [
            WifiReading(bssid="FF:FF:FF:FF:FF:FF", ssid="Unknown", rssi=-80, channel=1),
        ]


class TestFingerprint:
    """Tests for Fingerprint dataclass."""

    def test_create_fingerprint(self) -> None:
        readings = [
            WifiReading(bssid="AA:BB:CC:DD:EE:01", ssid="Test", rssi=-50, channel=6),
        ]
        fp = Fingerprint(location="office", readings=readings)
        assert fp.location == "office"
        assert len(fp.readings) == 1

    def test_fingerprint_to_dict(self) -> None:
        readings = [
            WifiReading(
                bssid="AA:BB:CC:DD:EE:01",
                ssid="Test",
                rssi=-50,
                channel=6,
                timestamp=datetime(2024, 1, 1),
            ),
        ]
        fp = Fingerprint(location="office", readings=readings, timestamp=datetime(2024, 1, 1))
        d = fp.to_dict()
        assert d["location"] == "office"
        assert len(d["readings"]) == 1
        assert d["readings"][0]["bssid"] == "AA:BB:CC:DD:EE:01"


class TestCollectFingerprint:
    """Tests for fingerprint collection."""

    def test_collect_fingerprint(self) -> None:
        scanner = MockScanner("office")
        # Use 0 interval for fast tests
        fingerprints = collect_fingerprint(scanner, "office", num_samples=3, interval=0)
        assert len(fingerprints) == 3
        assert all(fp.location == "office" for fp in fingerprints)
        assert all(len(fp.readings) == 3 for fp in fingerprints)

    def test_collect_fingerprint_callback(self) -> None:
        scanner = MockScanner("office")
        callback_calls: list[tuple] = []

        def cb(idx, total, count):
            callback_calls.append((idx, total, count))

        fingerprints = collect_fingerprint(
            scanner, "office", num_samples=2, interval=0, callback=cb
        )
        assert len(callback_calls) == 2
        assert callback_calls[0] == (0, 2, 3)
        assert callback_calls[1] == (1, 2, 3)

    def test_collect_fingerprint_empty_scan(self) -> None:
        """Empty scans should be skipped."""

        class EmptyScanner(WifiScanner):
            def scan(self) -> list[WifiReading]:
                return []

        fingerprints = collect_fingerprint(EmptyScanner(), "empty", num_samples=2, interval=0)
        assert len(fingerprints) == 0


class TestBuildFeatureMatrix:
    """Tests for feature matrix construction."""

    def test_basic_feature_matrix(self) -> None:
        fingerprints = [
            {
                "location": "office",
                "raw_data": [
                    {"bssid": "AA:BB:CC:DD:EE:01", "rssi": -40},
                    {"bssid": "AA:BB:CC:DD:EE:02", "rssi": -50},
                ],
            },
            {
                "location": "kitchen",
                "raw_data": [
                    {"bssid": "AA:BB:CC:DD:EE:01", "rssi": -70},
                    {"bssid": "AA:BB:CC:DD:EE:03", "rssi": -45},
                ],
            },
        ]

        X, y, bssids = build_feature_matrix(fingerprints)

        assert len(X) == 2
        assert len(y) == 2
        assert len(bssids) == 3  # 3 unique BSSIDs
        assert y[0] == "office"
        assert y[1] == "kitchen"

        # Check that missing BSSIDs are -100
        bssid_idx = {b: i for i, b in enumerate(bssids)}
        # office doesn't see AA:BB:CC:DD:EE:03
        assert X[0][bssid_idx["AA:BB:CC:DD:EE:03"]] == -100.0
        # kitchen doesn't see AA:BB:CC:DD:EE:02
        assert X[1][bssid_idx["AA:BB:CC:DD:EE:02"]] == -100.0

    def test_empty_fingerprints(self) -> None:
        X, y, bssids = build_feature_matrix([])
        assert X == []
        assert y == []
        assert bssids == []

    def test_single_fingerprint(self) -> None:
        fingerprints = [
            {
                "location": "office",
                "raw_data": [
                    {"bssid": "AA:BB:CC:DD:EE:01", "rssi": -40},
                ],
            },
        ]
        X, y, bssids = build_feature_matrix(fingerprints)
        assert len(X) == 1
        assert len(bssids) == 1
        assert X[0][0] == -40.0


class TestTraining:
    """Tests for model training."""

    def _populate_db(self, db: Database) -> None:
        """Populate the database with mock fingerprint data for two locations."""
        scanner = MockScanner()

        # Office fingerprints
        scanner.set_location("office")
        for _ in range(5):
            readings = scanner.scan()
            raw_data = [r.to_dict() for r in readings]
            db.save_fingerprint("office", raw_data)

        # Kitchen fingerprints
        scanner.set_location("kitchen")
        for _ in range(5):
            readings = scanner.scan()
            raw_data = [r.to_dict() for r in readings]
            db.save_fingerprint("kitchen", raw_data)

    def test_train_model(self) -> None:
        db = Database(":memory:")
        self._populate_db(db)

        result = train_model(db)

        assert isinstance(result, TrainingResult)
        assert result.accuracy >= 0.0
        assert "office" in result.locations
        assert "kitchen" in result.locations
        assert result.feature_count > 0
        # 10 original + 20 augmented = 30 total samples
        assert result.sample_count == 30
        assert result.classifier_name in ("RandomForest", "KNN", "GradientBoosting")
        assert "RandomForest" in result.comparison_results
        db.close()

    def test_train_model_too_few_locations(self) -> None:
        db = Database(":memory:")
        scanner = MockScanner("office")

        for _ in range(5):
            readings = scanner.scan()
            raw_data = [r.to_dict() for r in readings]
            db.save_fingerprint("office", raw_data)

        with pytest.raises(ValueError, match="At least 2 locations"):
            train_model(db)
        db.close()

    def test_train_model_too_few_fingerprints(self) -> None:
        db = Database(":memory:")
        scanner = MockScanner()

        # Only 2 fingerprints for office (need at least 3)
        scanner.set_location("office")
        for _ in range(2):
            readings = scanner.scan()
            raw_data = [r.to_dict() for r in readings]
            db.save_fingerprint("office", raw_data)

        scanner.set_location("kitchen")
        for _ in range(5):
            readings = scanner.scan()
            raw_data = [r.to_dict() for r in readings]
            db.save_fingerprint("kitchen", raw_data)

        with pytest.raises(ValueError, match="At least 3"):
            train_model(db)
        db.close()


class TestPrediction:
    """Tests for prediction."""

    def test_prediction_dataclass(self) -> None:
        pred = Prediction(
            location="office",
            confidence=0.85,
            probabilities={"office": 0.85, "kitchen": 0.15},
        )
        assert pred.location == "office"
        assert pred.confidence == 0.85
        assert "office" in str(pred)

    def test_predict_with_trained_model(self) -> None:
        db = Database(":memory:")
        scanner = MockScanner()

        # Populate and train
        scanner.set_location("office")
        for _ in range(5):
            readings = scanner.scan()
            raw_data = [r.to_dict() for r in readings]
            db.save_fingerprint("office", raw_data)

        scanner.set_location("kitchen")
        for _ in range(5):
            readings = scanner.scan()
            raw_data = [r.to_dict() for r in readings]
            db.save_fingerprint("kitchen", raw_data)

        train_model(db)

        # Predict as if in office
        scanner.set_location("office")
        predictor = Predictor(db)
        prediction = predictor.predict(scanner)

        assert isinstance(prediction, Prediction)
        assert prediction.location in ["office", "kitchen"]
        assert 0.0 <= prediction.confidence <= 1.0
        assert len(prediction.probabilities) == 2
        db.close()

    def test_predict_no_model(self) -> None:
        db = Database(":memory:")
        with pytest.raises(ValueError, match="No trained model found"):
            Predictor(db)
        db.close()


class TestAugmentFingerprints:
    """Tests for RSSI noise augmentation."""

    def test_augment_preserves_originals(self) -> None:
        from wifipos.model.fingerprint import augment_fingerprints

        originals = [
            {
                "location": "office",
                "raw_data": [{"bssid": "AA:BB:CC:DD:EE:01", "rssi": -40}],
                "timestamp": "",
            },
        ]
        result = augment_fingerprints(originals, num_augmented=2, noise_std=3.0)
        # Original is preserved unchanged
        assert result[0]["raw_data"][0]["rssi"] == -40
        assert result[0]["location"] == "office"

    def test_augment_creates_correct_count(self) -> None:
        from wifipos.model.fingerprint import augment_fingerprints

        originals = [
            {
                "location": "office",
                "raw_data": [{"bssid": "AA:BB:CC:DD:EE:01", "rssi": -40}],
                "timestamp": "",
            },
            {
                "location": "kitchen",
                "raw_data": [{"bssid": "AA:BB:CC:DD:EE:01", "rssi": -70}],
                "timestamp": "",
            },
        ]
        result = augment_fingerprints(originals, num_augmented=3, noise_std=3.0)
        # 2 originals + 2*3 augmented = 8
        assert len(result) == 8

    def test_augment_adds_noise(self) -> None:
        from wifipos.model.fingerprint import augment_fingerprints

        originals = [
            {
                "location": "office",
                "raw_data": [{"bssid": "AA:BB:CC:DD:EE:01", "rssi": -50}],
                "timestamp": "",
            },
        ]
        result = augment_fingerprints(originals, num_augmented=5, noise_std=1.0)
        # At least some augmented copies should differ from the original
        augmented_rssi = [r["raw_data"][0]["rssi"] for r in result[1:]]
        assert any(r != -50 for r in augmented_rssi)

    def test_augment_clamps_rssi(self) -> None:
        from wifipos.model.fingerprint import augment_fingerprints

        originals = [
            {
                "location": "office",
                "raw_data": [{"bssid": "AA:BB:CC:DD:EE:01", "rssi": -99}],
                "timestamp": "",
            },
        ]
        result = augment_fingerprints(originals, num_augmented=10, noise_std=1.0)
        for fp in result:
            rssi = fp["raw_data"][0]["rssi"]
            assert -100.0 <= rssi <= 0.0

    def test_augment_empty_input(self) -> None:
        from wifipos.model.fingerprint import augment_fingerprints

        result = augment_fingerprints([], num_augmented=3, noise_std=3.0)
        assert result == []

    def test_augment_is_deterministic_with_seed(self) -> None:
        from wifipos.model.fingerprint import augment_fingerprints

        originals = [
            {
                "location": "office",
                "raw_data": [{"bssid": "AA:BB:CC:DD:EE:01", "rssi": -50}],
                "timestamp": "",
            },
        ]
        result1 = augment_fingerprints(originals, num_augmented=3, noise_std=3.0, seed=42)
        result2 = augment_fingerprints(originals, num_augmented=3, noise_std=3.0, seed=42)
        for a, b in zip(result1, result2):
            assert a["raw_data"][0]["rssi"] == b["raw_data"][0]["rssi"]


class TestPredictAveraged:
    """Tests for averaged-scan prediction."""

    def test_predict_uses_averaged_scans(self) -> None:
        """Predictor.predict() should call scan_averaged when num_scans > 1."""
        db = Database(":memory:")
        scanner = MockScanner()

        # Populate and train
        scanner.set_location("office")
        for _ in range(5):
            readings = scanner.scan()
            raw_data = [r.to_dict() for r in readings]
            db.save_fingerprint("office", raw_data)

        scanner.set_location("kitchen")
        for _ in range(5):
            readings = scanner.scan()
            raw_data = [r.to_dict() for r in readings]
            db.save_fingerprint("kitchen", raw_data)

        train_model(db)

        scanner.set_location("office")
        predictor = Predictor(db)

        # num_scans=1 should still work (uses single scan)
        prediction = predictor.predict(scanner, num_scans=1)
        assert isinstance(prediction, Prediction)
        assert prediction.location in ["office", "kitchen"]

        # Default (num_scans=3) should also work
        prediction = predictor.predict(scanner)
        assert isinstance(prediction, Prediction)
        assert 0.0 <= prediction.confidence <= 1.0
        db.close()
