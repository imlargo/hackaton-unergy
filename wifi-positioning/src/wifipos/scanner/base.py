"""Abstract base class for WiFi scanners."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class WifiReading:
    """A single WiFi access point reading from a scan."""

    bssid: str
    ssid: str | None
    rssi: int
    channel: int | None = None
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """Convert to a dictionary for JSON serialization."""
        return {
            "bssid": self.bssid,
            "ssid": self.ssid,
            "rssi": self.rssi,
            "channel": self.channel,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> WifiReading:
        """Create a WifiReading from a dictionary."""
        return cls(
            bssid=data["bssid"],
            ssid=data.get("ssid"),
            rssi=data["rssi"],
            channel=data.get("channel"),
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


class WifiScanner(ABC):
    """Abstract base class for WiFi scanners.

    Subclasses must implement the `scan()` method to return a list
    of WifiReading objects from the platform's WiFi interface.
    """

    @abstractmethod
    def scan(self) -> list[WifiReading]:
        """Perform a WiFi scan and return a list of detected networks.

        Returns:
            A list of WifiReading objects, one per detected access point.

        Raises:
            PermissionError: If the scanner lacks required permissions.
            RuntimeError: If the WiFi interface is unavailable or off.
        """

    def scan_averaged(self, num_scans: int = 3, interval: float = 1.0) -> list[WifiReading]:
        """Perform multiple scans and average the RSSI values.

        Args:
            num_scans: Number of scans to perform.
            interval: Seconds to wait between scans.

        Returns:
            A list of WifiReading objects with averaged RSSI values.
        """
        import time

        all_readings: dict[str, list[int]] = {}
        latest_readings: dict[str, WifiReading] = {}

        for i in range(num_scans):
            readings = self.scan()
            for reading in readings:
                if reading.bssid not in all_readings:
                    all_readings[reading.bssid] = []
                all_readings[reading.bssid].append(reading.rssi)
                latest_readings[reading.bssid] = reading

            if i < num_scans - 1:
                time.sleep(interval)

        averaged: list[WifiReading] = []
        for bssid, rssi_values in all_readings.items():
            base = latest_readings[bssid]
            avg_rssi = round(sum(rssi_values) / len(rssi_values))
            averaged.append(
                WifiReading(
                    bssid=bssid,
                    ssid=base.ssid,
                    rssi=avg_rssi,
                    channel=base.channel,
                    timestamp=base.timestamp,
                )
            )

        return averaged
