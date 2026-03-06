"""macOS WiFi scanner using CoreWLAN framework via pyobjc."""

from __future__ import annotations

import logging

from wifipos.scanner.base import WifiReading, WifiScanner

logger = logging.getLogger(__name__)


class MacOSScanner(WifiScanner):
    """WiFi scanner for macOS using CoreWLAN framework.

    Requires pyobjc-framework-CoreWLAN to be installed.
    On macOS 14+, Location Services authorization is required.
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

    def _check_location_services(self) -> None:
        """Check and warn about Location Services authorization on macOS 14+."""
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
        except ImportError:
            logger.debug(
                "CoreLocation not available. Cannot check Location Services status."
            )

    def scan(self) -> list[WifiReading]:
        """Perform a WiFi scan using CoreWLAN.

        Returns:
            A list of WifiReading objects for detected networks.

        Raises:
            PermissionError: If Location Services are not authorized.
            RuntimeError: If the scan fails.
        """
        self._check_location_services()

        networks, error = self._interface.scanForNetworksWithName_error_(None, None)

        if error:
            error_msg = str(error)
            if "permission" in error_msg.lower() or "authorization" in error_msg.lower():
                raise PermissionError(
                    "WiFi scanning permission denied. On macOS 14+, enable Location "
                    "Services for your terminal app in System Preferences > "
                    "Privacy & Security > Location Services."
                )
            raise RuntimeError(f"WiFi scan failed: {error_msg}")

        if not networks:
            logger.warning("No networks found during scan.")
            return []

        readings: list[WifiReading] = []
        for network in networks:
            bssid = network.bssid()
            ssid = network.ssid()

            if bssid is None:
                logger.warning(
                    "BSSID returned None for a network. This is common on macOS 14.4+ "
                    "without Location Services. Skipping this network."
                )
                continue

            if ssid is None:
                logger.warning(
                    f"SSID returned None for BSSID {bssid}. This may indicate "
                    "Location Services is not fully authorized."
                )

            readings.append(
                WifiReading(
                    bssid=bssid,
                    ssid=ssid,
                    rssi=network.rssiValue(),
                    channel=network.wlanChannel().channelNumber() if network.wlanChannel() else None,
                )
            )

        logger.info(f"macOS scan found {len(readings)} networks.")
        return readings
