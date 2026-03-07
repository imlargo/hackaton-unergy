"""WiFi integration service — adapter/wrapper around wifi-positioning module.

This service acts as the **only** integration point between the local server
and the frozen ``wifi-positioning/`` module.  It imports from ``wifipos``
(the installed package) and adapts its outputs into domain-friendly dicts
that can be stored alongside spaces.

IMPORTANT: The ``wifi-positioning/`` directory and its contents must NEVER
be modified.  This wrapper consumes it read-only.

When the WiFi module is not available (e.g. in CI or environments without
WiFi hardware), the service attempts a **native** WiFi scan using
``nmcli`` or ``iwlist`` (Linux).  Only if that also fails does it fall
back to mock data so the rest of the backend can still be developed and
tested.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Try to import from the wifipos package (installed from wifi-positioning/)
# ---------------------------------------------------------------------------
_WIFIPOS_AVAILABLE = False

try:
    from wifipos.model.predictor import Predictor  # noqa: F401
    from wifipos.scanner import WifiReading, WifiScanner  # noqa: F401
    from wifipos.storage.database import Database as WifiDatabase  # noqa: F401
    from wifipos.utils.platform import get_scanner  # noqa: F401

    _WIFIPOS_AVAILABLE = True
    logger.info("wifi-positioning module loaded successfully.")
except ImportError:
    logger.warning(
        "wifi-positioning module not available. "
        "Will attempt native WiFi scanning."
    )


# ---------------------------------------------------------------------------
# Native Linux WiFi scanning (fallback when wifipos is not installed)
# ---------------------------------------------------------------------------

def _scan_nmcli() -> list[dict[str, Any]] | None:
    """Scan WiFi networks via ``nmcli`` (NetworkManager CLI).

    Returns a list of reading dicts or *None* if nmcli is unavailable.
    """
    if shutil.which("nmcli") is None:
        return None

    try:
        result = subprocess.run(
            [
                "nmcli", "-t", "-f",
                "BSSID,SSID,SIGNAL,CHAN",
                "device", "wifi", "list", "--rescan", "yes",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            logger.warning("nmcli scan failed: %s", result.stderr.strip())
            return None

        readings: list[dict[str, Any]] = []
        for line in result.stdout.strip().splitlines():
            if not line.strip():
                continue
            # nmcli escapes colons in BSSIDs as \:
            parts = line.replace(r"\:", "##COLON##").split(":")
            parts = [p.replace("##COLON##", ":") for p in parts]
            if len(parts) < 4:
                continue
            bssid = parts[0].strip()
            ssid = parts[1].strip()
            try:
                signal_pct = int(parts[2].strip())
                channel = int(parts[3].strip())
            except ValueError:
                continue
            # Approximate dBm conversion: 0% ≈ -100 dBm, 100% ≈ -30 dBm
            rssi = int(-100 + signal_pct * 0.7)
            readings.append({
                "bssid": bssid,
                "ssid": ssid,
                "rssi": rssi,
                "channel": channel,
            })
        return readings if readings else None
    except Exception as exc:
        logger.warning("nmcli scan error: %s", exc)
        return None


def _scan_iwlist() -> list[dict[str, Any]] | None:
    """Scan WiFi networks via ``iwlist`` (wireless-tools).

    Returns a list of reading dicts or *None* if iwlist is unavailable.
    """
    if shutil.which("iwlist") is None:
        return None

    # Determine the wireless interface
    iface = _detect_wireless_iface()
    if iface is None:
        return None

    try:
        result = subprocess.run(
            ["iwlist", iface, "scan"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            logger.warning("iwlist scan failed: %s", result.stderr.strip())
            return None

        readings: list[dict[str, Any]] = []
        current: dict[str, Any] = {}
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("Cell"):
                if current.get("bssid"):
                    readings.append(current)
                bssid_match = re.search(r"Address:\s*(\S+)", line)
                current = {
                    "bssid": bssid_match.group(1) if bssid_match else "",
                    "ssid": "",
                    "rssi": 0,
                    "channel": 0,
                }
            elif "ESSID:" in line:
                m = re.search(r'ESSID:"([^"]*)"', line)
                if m:
                    current["ssid"] = m.group(1)
            elif "Signal level=" in line:
                m = re.search(r"Signal level=(-?\d+)", line)
                if m:
                    current["rssi"] = int(m.group(1))
            elif "Channel:" in line:
                m = re.search(r"Channel:(\d+)", line)
                if m:
                    current["channel"] = int(m.group(1))
        if current.get("bssid"):
            readings.append(current)
        return readings if readings else None
    except Exception as exc:
        logger.warning("iwlist scan error: %s", exc)
        return None


def _detect_wireless_iface() -> str | None:
    """Return the first wireless interface name (e.g. wlan0, wlp2s0)."""
    try:
        result = subprocess.run(
            ["iw", "dev"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("Interface "):
                return stripped.split()[1]
    except Exception:
        pass
    # Fallback — check /sys/class/net
    try:
        for name in os.listdir("/sys/class/net"):
            if name.startswith(("wlan", "wlp", "wlx")):
                return name
    except Exception:
        pass
    return None


def _native_wifi_scan() -> dict[str, Any] | None:
    """Attempt a native WiFi scan using system tools.

    Returns a scan-result dict (same shape as ``_scan_real`` output)
    or *None* if no scanner is available / no networks found.
    """
    readings = _scan_nmcli()
    if readings is None:
        readings = _scan_iwlist()
    if readings is None:
        return None
    return {
        "networks_detected": len(readings),
        "readings": readings,
        "source": "native_linux",
    }


class WiFiIntegrationService:
    """Adapter that wraps ``wifipos`` functionality for the local API.

    Provides:
    * ``scan_current_environment()`` — capture nearby WiFi networks
    * ``get_setup_instructions()``   — guide the user through space registration
    * ``get_current_location()``     — predict location using a trained model
    """

    def __init__(self) -> None:
        self._scanner: Any | None = None
        if _WIFIPOS_AVAILABLE:
            try:
                self._scanner = get_scanner()
                logger.info(f"WiFi scanner initialized: {type(self._scanner).__name__}")
            except Exception as exc:
                logger.warning(f"Could not initialize WiFi scanner: {exc}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan_current_environment(self) -> dict[str, Any]:
        """Perform a WiFi scan and return a summary dict.

        The returned dict is stored as ``wifi_metadata`` on a Space.

        Priority:
        1. wifipos scanner (if installed and working)
        2. Native Linux scan via nmcli / iwlist
        3. Mock data (last resort — clearly flagged)
        """
        if self._scanner is not None:
            return self._scan_real()

        native = _native_wifi_scan()
        if native is not None:
            logger.info(
                "Native WiFi scan: %d networks detected.",
                native["networks_detected"],
            )
            return native

        return self._scan_mock()

    def get_setup_instructions(self) -> list[dict[str, str]]:
        """Return step-by-step instructions for space registration."""
        return [
            {
                "step": "1",
                "title": "Ubicarse en el espacio",
                "description": (
                    "Dirígete al espacio que deseas registrar "
                    "(habitación, oficina, cocina, etc.)."
                ),
            },
            {
                "step": "2",
                "title": "Asegurar conexión WiFi",
                "description": (
                    "Verifica que tu dispositivo esté conectado a una red WiFi. "
                    "El sistema usa las señales WiFi cercanas para identificar "
                    "tu ubicación."
                ),
            },
            {
                "step": "3",
                "title": "Iniciar escaneo",
                "description": (
                    "Presiona el botón 'Registrar espacio actual'. "
                    "El sistema capturará las señales WiFi de tu entorno."
                ),
            },
            {
                "step": "4",
                "title": "Asignar nombre y tipo",
                "description": (
                    "Dale un nombre descriptivo al espacio (p. ej. 'Cocina') "
                    "y selecciona el tipo (habitación, oficina, garaje, etc.)."
                ),
            },
            {
                "step": "5",
                "title": "Confirmar registro",
                "description": (
                    "Revisa los datos y confirma. El espacio quedará guardado "
                    "junto con su huella WiFi para futuras detecciones."
                ),
            },
        ]

    def get_current_location(self) -> dict[str, Any] | None:
        """Predict the current location using a trained model.

        Returns None if no model is available yet.
        This is a placeholder that will work once the user has
        registered enough spaces and trained the positioning model.
        """
        if not _WIFIPOS_AVAILABLE or self._scanner is None:
            return {
                "location": "unknown",
                "confidence": 0.0,
                "note": "WiFi positioning module not available or no trained model.",
            }

        try:
            db = WifiDatabase()
            predictor = Predictor(db)
            prediction = predictor.predict(self._scanner)
            return {
                "location": prediction.location,
                "confidence": prediction.confidence,
                "probabilities": prediction.probabilities,
            }
        except ValueError:
            return {
                "location": "unknown",
                "confidence": 0.0,
                "note": "No trained model yet. Register more spaces first.",
            }
        except Exception as exc:
            logger.error(f"Location prediction failed: {exc}")
            return None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _scan_real(self) -> dict[str, Any]:
        """Perform a real WiFi scan via the wifipos scanner."""
        try:
            readings = self._scanner.scan()
            return {
                "networks_detected": len(readings),
                "readings": [
                    {
                        "bssid": r.bssid,
                        "ssid": r.ssid,
                        "rssi": r.rssi,
                        "channel": r.channel,
                    }
                    for r in readings
                ],
                "source": "wifipos_scanner",
            }
        except Exception as exc:
            logger.error(f"WiFi scan failed: {exc}")
            # Try native fallback before resorting to mock
            native = _native_wifi_scan()
            if native is not None:
                return native
            return self._scan_mock()

    @staticmethod
    def _scan_mock() -> dict[str, Any]:
        """Return mock WiFi scan data for development/testing."""
        return {
            "networks_detected": 3,
            "readings": [
                {
                    "bssid": "AA:BB:CC:DD:EE:01",
                    "ssid": "HomeNetwork",
                    "rssi": -45,
                    "channel": 6,
                },
                {
                    "bssid": "AA:BB:CC:DD:EE:02",
                    "ssid": "OfficeNet",
                    "rssi": -62,
                    "channel": 11,
                },
                {
                    "bssid": "AA:BB:CC:DD:EE:03",
                    "ssid": "Neighbor_5G",
                    "rssi": -78,
                    "channel": 36,
                },
            ],
            "source": "mock",
        }
