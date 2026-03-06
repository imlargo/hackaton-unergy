"""Tests for the WiFi scanner module."""

from __future__ import annotations

import sys
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from wifipos.scanner.base import WifiReading, WifiScanner


class MockScanner(WifiScanner):
    """A mock WiFi scanner for testing."""

    def __init__(self, readings: list[WifiReading] | None = None) -> None:
        self._readings = readings if readings is not None else self._default_readings()

    @staticmethod
    def _default_readings() -> list[WifiReading]:
        return [
            WifiReading(bssid="AA:BB:CC:DD:EE:01", ssid="TestNetwork1", rssi=-45, channel=6),
            WifiReading(bssid="AA:BB:CC:DD:EE:02", ssid="TestNetwork2", rssi=-60, channel=11),
            WifiReading(bssid="AA:BB:CC:DD:EE:03", ssid="TestNetwork3", rssi=-75, channel=1),
            WifiReading(bssid="AA:BB:CC:DD:EE:04", ssid=None, rssi=-80, channel=36),
        ]

    def scan(self) -> list[WifiReading]:
        return list(self._readings)


class TestWifiReading:
    """Tests for WifiReading dataclass."""

    def test_create_reading(self) -> None:
        reading = WifiReading(bssid="AA:BB:CC:DD:EE:FF", ssid="Test", rssi=-50, channel=6)
        assert reading.bssid == "AA:BB:CC:DD:EE:FF"
        assert reading.ssid == "Test"
        assert reading.rssi == -50
        assert reading.channel == 6

    def test_create_reading_optional_fields(self) -> None:
        reading = WifiReading(bssid="AA:BB:CC:DD:EE:FF", ssid=None, rssi=-50)
        assert reading.ssid is None
        assert reading.channel is None

    def test_to_dict(self) -> None:
        reading = WifiReading(
            bssid="AA:BB:CC:DD:EE:FF",
            ssid="Test",
            rssi=-50,
            channel=6,
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
        )
        d = reading.to_dict()
        assert d["bssid"] == "AA:BB:CC:DD:EE:FF"
        assert d["ssid"] == "Test"
        assert d["rssi"] == -50
        assert d["channel"] == 6
        assert d["timestamp"] == "2024-01-01T12:00:00"

    def test_from_dict(self) -> None:
        data = {
            "bssid": "AA:BB:CC:DD:EE:FF",
            "ssid": "Test",
            "rssi": -50,
            "channel": 6,
            "timestamp": "2024-01-01T12:00:00",
        }
        reading = WifiReading.from_dict(data)
        assert reading.bssid == "AA:BB:CC:DD:EE:FF"
        assert reading.rssi == -50

    def test_roundtrip(self) -> None:
        original = WifiReading(
            bssid="AA:BB:CC:DD:EE:FF",
            ssid="Test",
            rssi=-50,
            channel=6,
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
        )
        restored = WifiReading.from_dict(original.to_dict())
        assert original.bssid == restored.bssid
        assert original.ssid == restored.ssid
        assert original.rssi == restored.rssi
        assert original.channel == restored.channel


class TestMockScanner:
    """Tests for the MockScanner."""

    def test_scan_returns_readings(self) -> None:
        scanner = MockScanner()
        readings = scanner.scan()
        assert len(readings) == 4
        assert all(isinstance(r, WifiReading) for r in readings)

    def test_scan_custom_readings(self) -> None:
        custom = [WifiReading(bssid="FF:FF:FF:FF:FF:FF", ssid="Custom", rssi=-30, channel=1)]
        scanner = MockScanner(readings=custom)
        readings = scanner.scan()
        assert len(readings) == 1
        assert readings[0].ssid == "Custom"

    def test_scan_empty(self) -> None:
        scanner = MockScanner(readings=[])
        readings = scanner.scan()
        assert readings == []


class TestScannerAbstraction:
    """Tests for the WifiScanner ABC."""

    def test_cannot_instantiate_abc(self) -> None:
        with pytest.raises(TypeError):
            WifiScanner()  # type: ignore[abstract]

    def test_mock_is_subclass(self) -> None:
        assert issubclass(MockScanner, WifiScanner)


class TestPlatformDetection:
    """Tests for platform detection and scanner factory."""

    def test_detect_platform_linux(self) -> None:
        from wifipos.utils.platform import detect_platform

        with patch.object(sys, "platform", "linux"):
            assert detect_platform() == "linux"

    def test_detect_platform_macos(self) -> None:
        from wifipos.utils.platform import detect_platform

        with patch.object(sys, "platform", "darwin"):
            assert detect_platform() == "macos"

    def test_detect_platform_windows(self) -> None:
        from wifipos.utils.platform import detect_platform

        with patch.object(sys, "platform", "win32"):
            assert detect_platform() == "windows"

    def test_detect_platform_unsupported(self) -> None:
        from wifipos.utils.platform import detect_platform

        with patch.object(sys, "platform", "freebsd"):
            with pytest.raises(RuntimeError, match="Unsupported platform"):
                detect_platform()


class TestLinuxScannerParsing:
    """Tests for Linux scanner nmcli/iwlist output parsing."""

    def test_nmcli_parsing(self) -> None:
        from wifipos.scanner.linux import LinuxScanner

        # Directly test parsing by mocking subprocess and shutil
        with patch("shutil.which", return_value="/usr/bin/nmcli"):
            scanner = LinuxScanner()

        mock_output = (
            "AA\\:BB\\:CC\\:DD\\:EE\\:01:TestNetwork1:85:6\n"
            "AA\\:BB\\:CC\\:DD\\:EE\\:02:TestNetwork2:60:11\n"
        )
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = mock_output
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            readings = scanner.scan()

        assert len(readings) == 2
        assert readings[0].bssid == "AA:BB:CC:DD:EE:01"
        assert readings[0].ssid == "TestNetwork1"
        assert readings[0].channel == 6

    def test_iwlist_parsing(self) -> None:
        from wifipos.scanner.linux import LinuxScanner

        with patch("shutil.which", side_effect=lambda x: "/usr/sbin/iwlist" if x == "iwlist" else None):
            scanner = LinuxScanner()

        mock_output = """
wlan0     Scan completed :
          Cell 01 - Address: AA:BB:CC:DD:EE:01
                    Channel:6
                    ESSID:"TestNetwork1"
                    Signal level=-45 dBm
          Cell 02 - Address: AA:BB:CC:DD:EE:02
                    Channel:11
                    ESSID:"TestNetwork2"
                    Signal level=-60 dBm
"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = mock_output
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            readings = scanner.scan()

        assert len(readings) == 2
        assert readings[0].bssid == "AA:BB:CC:DD:EE:01"
        assert readings[0].ssid == "TestNetwork1"
        assert readings[0].rssi == -45
        assert readings[0].channel == 6


class TestMacOSScannerTransientErrors:
    """Tests for macOS scanner transient error detection."""

    def test_resource_busy_is_transient(self) -> None:
        from wifipos.scanner.macos import MacOSScanner

        assert MacOSScanner._is_transient_error(
            'Error Domain=NSPOSIXErrorDomain Code=16 "Resource busy"'
        )

    def test_resource_busy_case_insensitive(self) -> None:
        from wifipos.scanner.macos import MacOSScanner

        assert MacOSScanner._is_transient_error("RESOURCE BUSY")

    def test_permission_error_is_not_transient(self) -> None:
        from wifipos.scanner.macos import MacOSScanner

        assert not MacOSScanner._is_transient_error("Permission denied")

    def test_unknown_error_is_not_transient(self) -> None:
        from wifipos.scanner.macos import MacOSScanner

        assert not MacOSScanner._is_transient_error("Something went wrong")


class TestMacOSScannerSSIDFallback:
    """Tests for SSID-based fallback when BSSIDs are unavailable."""

    def test_synthetic_bssid_is_deterministic(self) -> None:
        from wifipos.scanner.macos import MacOSScanner

        bssid1 = MacOSScanner._ssid_to_synthetic_bssid("MyWiFi", 6)
        bssid2 = MacOSScanner._ssid_to_synthetic_bssid("MyWiFi", 6)
        assert bssid1 == bssid2

    def test_synthetic_bssid_differs_by_ssid(self) -> None:
        from wifipos.scanner.macos import MacOSScanner

        bssid1 = MacOSScanner._ssid_to_synthetic_bssid("NetworkA", 6)
        bssid2 = MacOSScanner._ssid_to_synthetic_bssid("NetworkB", 6)
        assert bssid1 != bssid2

    def test_synthetic_bssid_differs_by_channel(self) -> None:
        from wifipos.scanner.macos import MacOSScanner

        bssid1 = MacOSScanner._ssid_to_synthetic_bssid("MyWiFi", 6)
        bssid2 = MacOSScanner._ssid_to_synthetic_bssid("MyWiFi", 11)
        assert bssid1 != bssid2

    def test_synthetic_bssid_starts_with_ssid_prefix(self) -> None:
        from wifipos.scanner.macos import MacOSScanner

        bssid = MacOSScanner._ssid_to_synthetic_bssid("MyWiFi", 6)
        assert bssid.startswith("ssid:")

    def test_synthetic_bssid_handles_none_channel(self) -> None:
        from wifipos.scanner.macos import MacOSScanner

        bssid = MacOSScanner._ssid_to_synthetic_bssid("MyWiFi", None)
        assert bssid.startswith("ssid:")
        # Should differ from a known channel
        bssid_with_ch = MacOSScanner._ssid_to_synthetic_bssid("MyWiFi", 6)
        assert bssid != bssid_with_ch


class TestCollectFingerprintErrorHandling:
    """Tests for collect_fingerprint handling RuntimeError from scanner."""

    def test_runtime_error_is_caught_and_skipped(self) -> None:
        """Scanner RuntimeError should be caught, not crash the collection."""
        from wifipos.model.fingerprint import collect_fingerprint

        class FailingScanner(WifiScanner):
            def scan(self) -> list[WifiReading]:
                raise RuntimeError("WiFi scan failed: Resource busy")

        fingerprints = collect_fingerprint(
            FailingScanner(), "test", num_samples=3, interval=0
        )
        assert len(fingerprints) == 0

    def test_partial_failure_collects_successful_samples(self) -> None:
        """Some scan failures should not prevent successful samples."""
        from wifipos.model.fingerprint import collect_fingerprint

        class PartialFailScanner(WifiScanner):
            def __init__(self) -> None:
                self._call_count = 0

            def scan(self) -> list[WifiReading]:
                self._call_count += 1
                if self._call_count % 2 == 0:
                    raise RuntimeError("Resource busy")
                return [
                    WifiReading(
                        bssid="AA:BB:CC:DD:EE:01", ssid="Test", rssi=-50, channel=6
                    )
                ]

        fingerprints = collect_fingerprint(
            PartialFailScanner(), "test", num_samples=4, interval=0
        )
        # Calls 1,3 succeed (odd), calls 2,4 fail (even)
        assert len(fingerprints) == 2

    def test_permission_error_still_propagates(self) -> None:
        """PermissionError should NOT be caught (not a RuntimeError)."""
        from wifipos.model.fingerprint import collect_fingerprint

        class PermissionScanner(WifiScanner):
            def scan(self) -> list[WifiReading]:
                raise PermissionError("WiFi scanning permission denied.")

        with pytest.raises(PermissionError):
            collect_fingerprint(
                PermissionScanner(), "test", num_samples=2, interval=0
            )


class TestWindowsScannerParsing:
    """Tests for Windows scanner netsh output parsing."""

    def test_netsh_parsing(self) -> None:
        from wifipos.scanner.windows import WindowsScanner

        scanner = WindowsScanner()

        mock_output = """
SSID 1 : TestNetwork1
    Network type            : Infrastructure
    Authentication          : WPA2-Personal
    Encryption              : CCMP
    BSSID 1                 : aa:bb:cc:dd:ee:01
         Signal             : 85%
         Channel            : 6

SSID 2 : TestNetwork2
    Network type            : Infrastructure
    Authentication          : WPA2-Personal
    Encryption              : CCMP
    BSSID 1                 : aa:bb:cc:dd:ee:02
         Signal             : 60%
         Channel            : 11
"""
        readings = scanner._parse_netsh_output(mock_output)

        assert len(readings) == 2
        assert readings[0].bssid == "aa:bb:cc:dd:ee:01"
        assert readings[0].ssid == "TestNetwork1"
        assert readings[0].channel == 6
        assert readings[1].bssid == "aa:bb:cc:dd:ee:02"
        assert readings[1].ssid == "TestNetwork2"
