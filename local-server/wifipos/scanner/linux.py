"""Linux WiFi scanner using nmcli or iwlist."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess

from wifipos.scanner.base import WifiReading, WifiScanner

logger = logging.getLogger(__name__)


class LinuxScanner(WifiScanner):
    """WiFi scanner for Linux using nmcli or iwlist.

    Prefers nmcli (NetworkManager) and falls back to iwlist if unavailable.
    """

    def __init__(self) -> None:
        self._use_nmcli = shutil.which("nmcli") is not None
        if not self._use_nmcli and shutil.which("iwlist") is None:
            raise RuntimeError(
                "Neither nmcli nor iwlist found. Install NetworkManager or "
                "wireless-tools for WiFi scanning."
            )

    def scan(self) -> list[WifiReading]:
        """Perform a WiFi scan using nmcli or iwlist.

        Returns:
            A list of WifiReading objects for detected networks.

        Raises:
            PermissionError: If scanning requires elevated privileges.
            RuntimeError: If the scan command fails.
        """
        if self._use_nmcli:
            return self._scan_nmcli()
        return self._scan_iwlist()

    def _scan_nmcli(self) -> list[WifiReading]:
        """Scan using nmcli."""
        try:
            result = subprocess.run(
                ["nmcli", "-t", "-f", "BSSID,SSID,SIGNAL,CHAN", "dev", "wifi", "list", "--rescan", "yes"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except FileNotFoundError as e:
            raise RuntimeError("nmcli not found.") from e
        except subprocess.TimeoutExpired as e:
            raise RuntimeError("WiFi scan timed out.") from e

        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "permission" in stderr.lower() or "not authorized" in stderr.lower():
                raise PermissionError(
                    "WiFi scanning requires appropriate permissions. "
                    "Try running with sudo or ensure your user is in the 'netdev' group."
                )
            if "wifi" in stderr.lower() and ("disabled" in stderr.lower() or "off" in stderr.lower()):
                raise RuntimeError(
                    "WiFi is turned off. Enable it with: nmcli radio wifi on"
                )
            raise RuntimeError(f"nmcli scan failed: {stderr}")

        readings: list[WifiReading] = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            # nmcli -t uses ':' as separator, but BSSID contains ':'
            # BSSID is XX\:XX\:XX\:XX\:XX\:XX in -t mode (escaped colons)
            # We need to handle escaped colons in BSSID
            parts = line.replace("\\:", "##COLON##").split(":")
            parts = [p.replace("##COLON##", ":") for p in parts]

            if len(parts) < 4:
                logger.debug(f"Skipping malformed nmcli line: {line}")
                continue

            bssid = parts[0].strip()
            ssid = parts[1].strip() or None
            try:
                # nmcli SIGNAL is 0-100 percentage, convert to approximate dBm
                signal_pct = int(parts[2].strip())
                rssi = self._signal_pct_to_dbm(signal_pct)
            except ValueError:
                logger.debug(f"Invalid signal value in nmcli output: {parts[2]}")
                continue
            try:
                channel = int(parts[3].strip()) if parts[3].strip() else None
            except ValueError:
                channel = None

            if bssid:
                readings.append(
                    WifiReading(bssid=bssid, ssid=ssid, rssi=rssi, channel=channel)
                )

        logger.info(f"nmcli scan found {len(readings)} networks.")
        return readings

    def _scan_iwlist(self) -> list[WifiReading]:
        """Scan using iwlist (fallback)."""
        try:
            result = subprocess.run(
                ["iwlist", "wlan0", "scan"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except FileNotFoundError as e:
            raise RuntimeError("iwlist not found.") from e
        except subprocess.TimeoutExpired as e:
            raise RuntimeError("WiFi scan timed out.") from e

        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "permission" in stderr.lower() or "operation not permitted" in stderr.lower():
                raise PermissionError(
                    "WiFi scanning requires root privileges with iwlist. "
                    "Try running with: sudo wifipos <command>"
                )
            raise RuntimeError(f"iwlist scan failed: {stderr}")

        readings: list[WifiReading] = []
        cells = re.split(r"Cell \d+ - ", result.stdout)

        for cell in cells[1:]:  # Skip text before first cell
            bssid_match = re.search(r"Address:\s*([0-9A-Fa-f:]+)", cell)
            ssid_match = re.search(r'ESSID:"([^"]*)"', cell)
            rssi_match = re.search(r"Signal level[=:](-?\d+)\s*dBm", cell)
            channel_match = re.search(r"Channel[:\s]*(\d+)", cell)

            if not bssid_match:
                continue

            bssid = bssid_match.group(1)
            ssid = ssid_match.group(1) if ssid_match else None
            rssi = int(rssi_match.group(1)) if rssi_match else -100
            channel = int(channel_match.group(1)) if channel_match else None

            readings.append(
                WifiReading(bssid=bssid, ssid=ssid, rssi=rssi, channel=channel)
            )

        logger.info(f"iwlist scan found {len(readings)} networks.")
        return readings

    @staticmethod
    def _signal_pct_to_dbm(signal_pct: int) -> int:
        """Convert a signal percentage (0-100) to approximate dBm.

        Uses a simple linear mapping: 100% -> -30 dBm, 0% -> -100 dBm.
        """
        return max(-100, min(-30, -100 + int(signal_pct * 0.7)))
