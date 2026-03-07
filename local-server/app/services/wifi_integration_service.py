"""WiFi integration service — adapter/wrapper around wifi-positioning module.

This service acts as the **only** integration point between the local server
and the ``wifipos`` module (copied from ``wifi-positioning/src/wifipos/``).

When a space is registered, this service:
1. Scans WiFi networks in the current environment.
2. Saves the scan as a fingerprint in the wifipos SQLite database.
3. Attempts to retrain the positioning model (if ≥2 locations with ≥3
   fingerprints each).

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
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Try to import from the wifipos package (copied into local-server/wifipos/)
# ---------------------------------------------------------------------------
_WIFIPOS_AVAILABLE = False
_WIFIPOS_IMPORT_ERROR: str | None = None

try:
    from wifipos.model.predictor import Predictor  # noqa: F401
    from wifipos.model.trainer import train_model  # noqa: F401
    from wifipos.scanner import WifiReading, WifiScanner  # noqa: F401
    from wifipos.storage.database import Database as WifiDatabase  # noqa: F401
    from wifipos.utils.platform import get_scanner  # noqa: F401

    _WIFIPOS_AVAILABLE = True
    logger.info("wifi-positioning module loaded successfully.")
except ImportError as exc:
    _WIFIPOS_IMPORT_ERROR = str(exc)
    logger.warning(
        "wifi-positioning module not available: %s. "
        "Fingerprints will NOT be saved. "
        "Fix: cd local-server && pip install -r requirements.txt",
        exc,
    )

# Default wifipos database path: local-server/data/wifipos.db
_DEFAULT_WIFIPOS_DB = Path(__file__).resolve().parent.parent.parent / "data" / "wifipos.db"

# Timeout for waiting on the tracking thread to stop.
_TRACKING_THREAD_JOIN_TIMEOUT = 10


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

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._scanner: Any | None = None
        self._db: Any | None = None

        # Tracking state
        self._tracking_active = False
        self._tracking_thread: threading.Thread | None = None
        self._tracking_lock = threading.Lock()
        self._latest_prediction: dict[str, Any] | None = None

        if _WIFIPOS_AVAILABLE:
            # Initialize wifipos database for fingerprint storage
            resolved = Path(db_path) if db_path else _DEFAULT_WIFIPOS_DB
            try:
                self._db = WifiDatabase(resolved)
                logger.info(f"WiFi positioning database at: {resolved}")
            except Exception as exc:
                logger.warning(f"Could not initialize wifipos database: {exc}")

            # Initialize platform-specific WiFi scanner
            try:
                self._scanner = get_scanner()
                logger.info(f"WiFi scanner initialized: {type(self._scanner).__name__}")
            except Exception as exc:
                logger.warning(f"Could not initialize WiFi scanner: {exc}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_diagnostics(self) -> dict[str, Any]:
        """Return a diagnostics dict showing the health of all wifipos sub-systems.

        Useful for debugging setup issues — exposed via ``GET /health/wifipos``.
        """
        diag: dict[str, Any] = {
            "wifipos_available": _WIFIPOS_AVAILABLE,
            "database_initialized": self._db is not None,
            "scanner_initialized": self._scanner is not None,
            "tracking_active": self._tracking_active,
        }

        if _WIFIPOS_IMPORT_ERROR:
            diag["import_error"] = _WIFIPOS_IMPORT_ERROR
            diag["fix"] = "cd local-server && pip install -r requirements.txt"

        # Check individual deps
        deps = {}
        for mod_name in ("joblib", "sklearn", "numpy"):
            try:
                __import__(mod_name)
                deps[mod_name] = "installed"
            except ImportError:
                deps[mod_name] = "MISSING"
        diag["dependencies"] = deps

        if self._db is not None:
            try:
                counts = self._db.get_fingerprint_count_by_location()
                diag["fingerprint_locations"] = dict(counts)
                diag["total_fingerprints"] = sum(counts.values())
            except Exception:
                diag["fingerprint_locations"] = {}
                diag["total_fingerprints"] = 0

            try:
                model = self._db.load_latest_model()
                diag["model_available"] = model is not None
            except Exception:
                diag["model_available"] = False

        return diag

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

    def save_fingerprint(self, location: str, wifi_metadata: dict[str, Any]) -> bool:
        """Save a WiFi scan as a fingerprint in the wifipos database.

        This is equivalent to what ``wifipos learn <location>`` does:
        the scan readings are stored so they can later be used for
        model training.

        Args:
            location: The space/location name (e.g. "Cocina").
            wifi_metadata: The dict returned by ``scan_current_environment()``.

        Returns:
            True if the fingerprint was saved, False otherwise.
        """
        if self._db is None:
            if _WIFIPOS_IMPORT_ERROR:
                logger.warning(
                    "wifipos database not available — fingerprint not saved "
                    "(import error: %s). "
                    "Fix: cd local-server && pip install -r requirements.txt",
                    _WIFIPOS_IMPORT_ERROR,
                )
            else:
                logger.warning(
                    "wifipos database not available — fingerprint not saved. "
                    "Fix: cd local-server && pip install -r requirements.txt",
                )
            return False

        readings = wifi_metadata.get("readings", [])
        if not readings:
            logger.warning("No WiFi readings to save as fingerprint.")
            return False

        try:
            self._db.save_fingerprint(location, readings, datetime.now())
            logger.info(
                "Saved fingerprint for '%s' with %d readings.",
                location,
                len(readings),
            )
            return True
        except Exception as exc:
            logger.error("Failed to save fingerprint: %s", exc)
            return False

    def try_train_model(self) -> dict[str, Any] | None:
        """Attempt to train the positioning model if enough data exists.

        Training requires ≥2 locations with ≥3 fingerprints each.
        This is called automatically after each space registration.

        Returns:
            A dict with training results (accuracy, locations, etc.),
            or None if training was skipped or failed.
        """
        if self._db is None:
            return None

        try:
            counts = self._db.get_fingerprint_count_by_location()
            if len(counts) < 2:
                logger.info(
                    "Training skipped: need ≥2 locations, have %d.",
                    len(counts),
                )
                return None

            for loc, count in counts.items():
                if count < 3:
                    logger.info(
                        "Training skipped: '%s' has only %d fingerprints (need ≥3).",
                        loc,
                        count,
                    )
                    return None

            result = train_model(self._db)
            logger.info(
                "Model trained: accuracy=%.2f, classifier=%s, locations=%s",
                result.accuracy,
                result.classifier_name,
                result.locations,
            )
            return {
                "accuracy": result.accuracy,
                "classifier": result.classifier_name,
                "locations": result.locations,
                "feature_count": result.feature_count,
                "sample_count": result.sample_count,
            }
        except Exception as exc:
            logger.error("Model training failed: %s", exc)
            return None

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
        Works once the user has registered enough spaces (≥2 locations
        with ≥3 fingerprints each) and the model has been auto-trained.
        """
        if not _WIFIPOS_AVAILABLE or self._scanner is None or self._db is None:
            return {
                "location": "unknown",
                "confidence": 0.0,
                "note": "WiFi positioning module not available or no trained model.",
            }

        try:
            predictor = Predictor(self._db)
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
    # Walk-mode fingerprint collection
    # ------------------------------------------------------------------

    def collect_and_save_fingerprints(
        self,
        location: str,
        num_samples: int = 20,
        interval: float = 2.0,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> dict[str, Any]:
        """Collect multiple WiFi fingerprints with walk/movement mode.

        Equivalent to ``wifipos learn <location> --walk --samples N``.
        The user should move around the space while samples are being
        collected so the model captures signal variability.

        Args:
            location: The space/location name (e.g. "Cocina").
            num_samples: Number of scans to collect.
            interval: Seconds between scans.
            progress_callback: Optional callable(saved_count, num_samples)
                invoked after each fingerprint is saved so callers can
                report real-time progress.

        Returns:
            A dict with collection results.
        """
        saved_count = 0

        def _report_progress() -> None:
            if progress_callback is not None:
                try:
                    progress_callback(saved_count, num_samples)
                except Exception:
                    logger.debug(
                        "Progress callback error (collection continues): %s",
                        location, exc_info=True,
                    )

        if self._scanner is not None and _WIFIPOS_AVAILABLE and self._db is not None:
            # Use the real wifipos collect_fingerprint
            from wifipos.model.fingerprint import collect_fingerprint

            logger.info(
                "  ▸ [walk] Using wifipos scanner for '%s' (%d samples, %.1fs interval).",
                location, num_samples, interval,
            )
            fingerprints = collect_fingerprint(
                scanner=self._scanner,
                location=location,
                num_samples=num_samples,
                interval=interval,
            )
            for i, fp in enumerate(fingerprints, 1):
                raw_data = [r.to_dict() for r in fp.readings]
                self._db.save_fingerprint(location, raw_data, fp.timestamp)
                saved_count += 1
                _report_progress()
                if i % 5 == 0 or i == num_samples:
                    logger.info(
                        "  ▸ [walk] '%s' sample %d/%d saved (%d networks).",
                        location, i, num_samples, len(raw_data),
                    )
        else:
            # Fallback: take multiple scans using native/mock
            # Skip sleep for mock data (CI/testing) since there's no real
            # signal variation to capture.
            first_scan = self.scan_current_environment()
            is_mock = first_scan.get("source") == "mock"
            self.save_fingerprint(location, first_scan)
            saved_count += 1
            _report_progress()
            logger.info(
                "  ▸ [walk] '%s' sample 1/%d saved (source=%s).",
                location, num_samples, first_scan.get("source", "unknown"),
            )
            for i in range(1, num_samples):
                if not is_mock:
                    time.sleep(interval)
                scan = self.scan_current_environment()
                self.save_fingerprint(location, scan)
                saved_count += 1
                _report_progress()
                if (i + 1) % 5 == 0 or i + 1 == num_samples:
                    logger.info(
                        "  ▸ [walk] '%s' sample %d/%d saved.",
                        location, i + 1, num_samples,
                    )

        logger.info(
            "Walk-mode collection for '%s': %d/%d fingerprints saved.",
            location,
            saved_count,
            num_samples,
        )
        return {
            "location": location,
            "samples_requested": num_samples,
            "fingerprints_saved": saved_count,
        }

    # ------------------------------------------------------------------
    # Tracking (continuous location prediction)
    # ------------------------------------------------------------------

    def start_tracking(self, interval: float = 3.0) -> dict[str, Any]:
        """Start continuous location tracking in a background thread.

        Equivalent to ``wifipos track --interval N``.

        Args:
            interval: Seconds between predictions.

        Returns:
            A dict with tracking status.
        """
        with self._tracking_lock:
            if self._tracking_active:
                return {"status": "already_running", "interval": interval}

            self._tracking_active = True
            self._latest_prediction = None
            self._tracking_thread = threading.Thread(
                target=self._tracking_loop,
                args=(interval,),
                daemon=True,
            )
            self._tracking_thread.start()
            logger.info("Tracking started (interval=%.1fs).", interval)
            return {"status": "started", "interval": interval}

    def stop_tracking(self) -> dict[str, Any]:
        """Stop the background tracking thread."""
        with self._tracking_lock:
            if not self._tracking_active:
                return {"status": "not_running"}

            self._tracking_active = False

        # Wait for the thread to finish (with timeout)
        if self._tracking_thread is not None:
            self._tracking_thread.join(timeout=_TRACKING_THREAD_JOIN_TIMEOUT)
            self._tracking_thread = None

        logger.info("Tracking stopped.")
        return {"status": "stopped"}

    def get_tracking_status(self) -> dict[str, Any]:
        """Return current tracking state and latest prediction."""
        return {
            "active": self._tracking_active,
            "latest_prediction": self._latest_prediction,
        }

    def _tracking_loop(self, interval: float) -> None:
        """Background loop that continuously predicts location."""
        logger.info("Tracking loop started.")
        while self._tracking_active:
            prediction = self.get_current_location()
            if prediction is not None:
                prediction["timestamp"] = datetime.now().isoformat()
                self._latest_prediction = prediction
            time.sleep(interval)
        logger.info("Tracking loop ended.")

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset_wifi_data(self) -> dict[str, Any]:
        """Delete all fingerprints and trained models from wifipos DB.

        Equivalent to ``wifipos reset``.
        """
        # Stop tracking first
        if self._tracking_active:
            self.stop_tracking()

        if self._db is None:
            return {"fingerprints_deleted": 0, "models_deleted": 0}

        try:
            self._db.reset()
            logger.info("WiFi positioning data reset.")
            return {"fingerprints_deleted": True, "models_deleted": True}
        except Exception as exc:
            logger.error("Failed to reset wifipos data: %s", exc)
            return {"error": str(exc)}

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
