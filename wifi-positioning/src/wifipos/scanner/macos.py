"""macOS WiFi scanner using CoreWLAN framework via pyobjc."""

from __future__ import annotations

import hashlib
import logging
import time

from wifipos.scanner.base import WifiReading, WifiScanner

logger = logging.getLogger(__name__)

MAX_SCAN_RETRIES = 3
INITIAL_RETRY_DELAY = 2.0


class MacOSScanner(WifiScanner):
    """WiFi scanner for macOS using CoreWLAN framework.

    Requires pyobjc-framework-CoreWLAN to be installed.
    On macOS 14+, Location Services authorization is required.
    When Location Services are unavailable, falls back to SSID-based
    identification with reduced accuracy.
    """

    def __init__(self) -> None:
        try:
            import CoreWLAN  # type: ignore[import-not-found]

            self._CoreWLAN = CoreWLAN
        except ImportError as e:
            raise RuntimeError(
                "pyobjc-framework-CoreWLAN is required on macOS. "
                "Try reinstalling the package: pip install -e . "
                "or install it manually: pip install pyobjc-framework-CoreWLAN"
            ) from e

        self._interface = CoreWLAN.CWWiFiClient.sharedWiFiClient().interface()
        if self._interface is None:
            raise RuntimeError(
                "No WiFi interface found. Ensure WiFi hardware is available."
            )
        self._location_services_warned = False
        self._ssid_fallback_warned = False

    def _check_location_services(self) -> None:
        """Check and warn about Location Services authorization on macOS 14+.

        Only warns once per scanner instance to avoid log spam.
        """
        if self._location_services_warned:
            return
        try:
            import CoreLocation  # type: ignore[import-not-found]

            manager = CoreLocation.CLLocationManager.alloc().init()
            status = CoreLocation.CLLocationManager.authorizationStatus()
            if status not in (3, 4):  # kCLAuthorizationStatusAuthorizedAlways/WhenInUse
                logger.warning(
                    "Location Services not authorized. On macOS 14+, WiFi scanning "
                    "requires Location Services. Enable it in System Preferences > "
                    "Privacy & Security > Location Services for your terminal app."
                )
                self._location_services_warned = True
        except ImportError:
            logger.debug(
                "CoreLocation not available. Cannot check Location Services status."
            )
            self._location_services_warned = True

    @staticmethod
    def _is_transient_error(error_msg: str) -> bool:
        """Check if a scan error is transient and worth retrying."""
        transient_keywords = ["resource busy", "code=16"]
        lower = error_msg.lower()
        return any(kw in lower for kw in transient_keywords)

    @staticmethod
    def _ssid_to_synthetic_bssid(ssid: str, channel: int | None) -> str:
        """Generate a deterministic synthetic BSSID from SSID and channel.

        Used as a fallback when real BSSIDs are unavailable (e.g. macOS 14.4+
        without Location Services).

        Args:
            ssid: The network SSID.
            channel: The WiFi channel number, or None.

        Returns:
            A synthetic BSSID string in the format ``ssid:<hash_prefix>``.
        """
        key = f"{ssid}:{channel if channel is not None else '?'}"
        h = hashlib.md5(key.encode()).hexdigest()[:12]  # noqa: S324
        return f"ssid:{h}"

    def scan(self) -> list[WifiReading]:
        """Perform a WiFi scan using CoreWLAN.

        Retries automatically on transient errors (e.g. "Resource busy")
        with exponential backoff. When BSSIDs are unavailable (macOS 14.4+
        without Location Services), falls back to SSID-based identification.

        Returns:
            A list of WifiReading objects for detected networks.

        Raises:
            PermissionError: If Location Services are not authorized.
            RuntimeError: If the scan fails after all retries.
        """
        self._check_location_services()

        last_error_msg = ""
        for attempt in range(MAX_SCAN_RETRIES):
            networks, error = self._interface.scanForNetworksWithName_error_(None, None)

            if error:
                error_msg = str(error)
                if "permission" in error_msg.lower() or "authorization" in error_msg.lower():
                    raise PermissionError(
                        "WiFi scanning permission denied. On macOS 14+, enable Location "
                        "Services for your terminal app in System Preferences > "
                        "Privacy & Security > Location Services."
                    )
                if self._is_transient_error(error_msg) and attempt < MAX_SCAN_RETRIES - 1:
                    delay = INITIAL_RETRY_DELAY * (2 ** attempt)
                    logger.warning(
                        f"WiFi interface temporarily busy (attempt "
                        f"{attempt + 1}/{MAX_SCAN_RETRIES}). This is normal "
                        f"when scanning rapidly. Retrying in {delay:.0f}s..."
                    )
                    last_error_msg = error_msg
                    time.sleep(delay)
                    continue
                raise RuntimeError(f"WiFi scan failed: {error_msg}")

            break
        else:
            # All retry attempts exhausted with transient errors;
            # last_error_msg is guaranteed set since we only reach here
            # after at least one transient error triggered a continue.
            raise RuntimeError(
                f"WiFi scan failed after {MAX_SCAN_RETRIES} attempts: {last_error_msg}"
            )

        if not networks:
            logger.warning("No networks found during scan.")
            return []

        readings: list[WifiReading] = []
        null_bssid_count = 0
        null_ssid_count = 0
        ssid_fallback_count = 0
        for network in networks:
            bssid = network.bssid()
            ssid = network.ssid()
            channel = network.wlanChannel().channelNumber() if network.wlanChannel() else None

            if bssid is None:
                null_bssid_count += 1
                # Fall back to SSID-based identification when BSSID is
                # unavailable (common on macOS 14.4+ without Location Services).
                if ssid is not None:
                    bssid = self._ssid_to_synthetic_bssid(ssid, channel)
                    ssid_fallback_count += 1
                else:
                    continue

            if ssid is None:
                null_ssid_count += 1

            readings.append(
                WifiReading(
                    bssid=bssid,
                    ssid=ssid,
                    rssi=network.rssiValue(),
                    channel=channel,
                )
            )

        if null_bssid_count > 0 and ssid_fallback_count > 0:
            if not self._ssid_fallback_warned:
                logger.warning(
                    f"Used SSID-based identification for {ssid_fallback_count} "
                    f"network(s) (no BSSID available). Positioning accuracy may "
                    f"be reduced. Enable Location Services for best results."
                )
                self._ssid_fallback_warned = True
        elif null_bssid_count > 0:
            logger.warning(
                f"Skipped {null_bssid_count} network(s) with null BSSID and no SSID."
            )
        if null_ssid_count > 0:
            logger.debug(
                f"{null_ssid_count} network(s) returned null SSID. "
                "This may indicate Location Services is not fully authorized."
            )

        logger.info(f"macOS scan found {len(readings)} networks.")
        return readings
