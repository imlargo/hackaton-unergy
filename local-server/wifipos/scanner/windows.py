"""Windows WiFi scanner using netsh."""

from __future__ import annotations

import logging
import re
import subprocess

from wifipos.scanner.base import WifiReading, WifiScanner

logger = logging.getLogger(__name__)


class WindowsScanner(WifiScanner):
    """WiFi scanner for Windows using netsh."""

    def scan(self) -> list[WifiReading]:
        """Perform a WiFi scan using netsh.

        Returns:
            A list of WifiReading objects for detected networks.

        Raises:
            PermissionError: If scanning requires elevated privileges.
            RuntimeError: If the scan command fails.
        """
        try:
            result = subprocess.run(
                ["netsh", "wlan", "show", "networks", "mode=bssid"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except FileNotFoundError as e:
            raise RuntimeError(
                "netsh not found. Ensure you are running on Windows "
                "with WiFi capabilities."
            ) from e
        except subprocess.TimeoutExpired as e:
            raise RuntimeError("WiFi scan timed out.") from e

        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "permission" in stderr.lower() or "access" in stderr.lower():
                raise PermissionError(
                    "WiFi scanning requires administrator privileges on this system."
                )
            raise RuntimeError(f"netsh scan failed: {stderr}")

        output = result.stdout
        if "WiFi is turned off" in output or "wireless" in output.lower() and "not running" in output.lower():
            raise RuntimeError(
                "WiFi is turned off. Enable it in Windows Settings > "
                "Network & Internet > Wi-Fi."
            )

        return self._parse_netsh_output(output)

    def _parse_netsh_output(self, output: str) -> list[WifiReading]:
        """Parse the output of netsh wlan show networks mode=bssid.

        The output format is:
            SSID 1 : NetworkName
                Network type  : Infrastructure
                Authentication: WPA2-Personal
                Encryption    : CCMP
                BSSID 1       : aa:bb:cc:dd:ee:ff
                     Signal   : 85%
                     Channel  : 6
        """
        readings: list[WifiReading] = []
        current_ssid: str | None = None

        # Split into lines and process
        lines = output.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Match SSID line
            ssid_match = re.match(r"^SSID\s+\d+\s*:\s*(.*)", line)
            if ssid_match:
                current_ssid = ssid_match.group(1).strip() or None
                i += 1
                continue

            # Match BSSID line
            bssid_match = re.match(r"^BSSID\s+\d+\s*:\s*([0-9a-fA-F:]+)", line)
            if bssid_match:
                bssid = bssid_match.group(1).strip()
                signal: int | None = None
                channel: int | None = None

                # Look at subsequent lines for signal and channel
                j = i + 1
                while j < len(lines) and j <= i + 5:
                    next_line = lines[j].strip()
                    signal_match = re.match(r"Signal\s*:\s*(\d+)%", next_line)
                    channel_match = re.match(r"Channel\s*:\s*(\d+)", next_line)

                    if signal_match:
                        signal_pct = int(signal_match.group(1))
                        signal = self._signal_pct_to_dbm(signal_pct)
                    elif channel_match:
                        channel = int(channel_match.group(1))

                    # Stop if we hit another SSID or BSSID
                    if re.match(r"^(SSID|BSSID)\s+\d+", next_line):
                        break
                    j += 1

                readings.append(
                    WifiReading(
                        bssid=bssid,
                        ssid=current_ssid,
                        rssi=signal if signal is not None else -100,
                        channel=channel,
                    )
                )

            i += 1

        logger.info(f"netsh scan found {len(readings)} networks.")
        return readings

    @staticmethod
    def _signal_pct_to_dbm(signal_pct: int) -> int:
        """Convert a signal percentage (0-100) to approximate dBm."""
        return max(-100, min(-30, -100 + int(signal_pct * 0.7)))
