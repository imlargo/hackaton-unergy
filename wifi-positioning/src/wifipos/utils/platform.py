"""OS detection and scanner factory."""

from __future__ import annotations

import logging
import sys

from wifipos.scanner.base import WifiScanner

logger = logging.getLogger(__name__)


def detect_platform() -> str:
    """Detect the current operating system.

    Returns:
        One of 'macos', 'linux', or 'windows'.

    Raises:
        RuntimeError: If the platform is not supported.
    """
    if sys.platform == "darwin":
        return "macos"
    elif sys.platform.startswith("linux"):
        return "linux"
    elif sys.platform == "win32":
        return "windows"
    else:
        raise RuntimeError(
            f"Unsupported platform: {sys.platform}. "
            "wifipos supports macOS, Linux, and Windows."
        )


def get_scanner() -> WifiScanner:
    """Create and return the appropriate WiFi scanner for the current platform.

    Returns:
        A WifiScanner instance for the detected platform.

    Raises:
        RuntimeError: If the platform is unsupported or scanner cannot be initialized.
    """
    platform = detect_platform()
    logger.info(f"Detected platform: {platform}")

    if platform == "macos":
        from wifipos.scanner.macos import MacOSScanner

        return MacOSScanner()
    elif platform == "linux":
        from wifipos.scanner.linux import LinuxScanner

        return LinuxScanner()
    elif platform == "windows":
        from wifipos.scanner.windows import WindowsScanner

        return WindowsScanner()
    else:
        raise RuntimeError(f"No scanner available for platform: {platform}")
