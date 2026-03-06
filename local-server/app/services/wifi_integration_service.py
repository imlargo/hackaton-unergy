"""WiFi integration service — adapter/wrapper around wifi-positioning module.

This service acts as the **only** integration point between the local server
and the frozen ``wifi-positioning/`` module.  It imports from ``wifipos``
(the installed package) and adapts its outputs into domain-friendly dicts
that can be stored alongside spaces.

IMPORTANT: The ``wifi-positioning/`` directory and its contents must NEVER
be modified.  This wrapper consumes it read-only.

When the WiFi module is not available (e.g. in CI or environments without
WiFi hardware), the service falls back to mock data so the rest of the
backend can still be developed and tested.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Try to import from the wifipos package (installed from wifi-positioning/)
# ---------------------------------------------------------------------------
_WIFIPOS_AVAILABLE = False

try:
    from wifipos.scanner import WifiReading, WifiScanner  # noqa: F401
    from wifipos.utils.platform import get_scanner  # noqa: F401

    _WIFIPOS_AVAILABLE = True
    logger.info("wifi-positioning module loaded successfully.")
except ImportError:
    logger.warning(
        "wifi-positioning module not available. "
        "Using mock WiFi data for development."
    )


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
        """
        if self._scanner is not None:
            return self._scan_real()
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
            from wifipos.model.predictor import Predictor
            from wifipos.storage.database import Database

            db = Database()
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
