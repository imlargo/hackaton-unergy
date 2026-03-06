"""WiFi fingerprint data collection and transformation."""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from wifipos.scanner.base import WifiReading, WifiScanner

logger = logging.getLogger(__name__)


@dataclass
class Fingerprint:
    """A WiFi fingerprint at a specific location."""

    location: str
    readings: list[WifiReading]
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """Convert to a dictionary for serialization."""
        return {
            "location": self.location,
            "readings": [r.to_dict() for r in self.readings],
            "timestamp": self.timestamp.isoformat(),
        }


def collect_fingerprint(
    scanner: WifiScanner,
    location: str,
    num_samples: int = 5,
    interval: float = 2.0,
    callback: Callable[[int, int, int], None] | None = None,
) -> list[Fingerprint]:
    """Collect WiFi fingerprints at a given location.

    Takes multiple WiFi scans at the specified location to capture signal
    variability. Each scan produces a separate Fingerprint.

    Args:
        scanner: The WiFi scanner to use.
        location: The location name/label.
        num_samples: Number of scans to collect.
        interval: Seconds to wait between scans.
        callback: Optional callback(sample_index, num_samples, reading_count)
                  called after each scan.

    Returns:
        A list of Fingerprint objects, one per scan.
    """
    fingerprints: list[Fingerprint] = []
    # After a scan failure, wait longer to let the WiFi hardware recover.
    failure_cooldown = max(interval * 2, 1.0)

    for i in range(num_samples):
        try:
            readings = scanner.scan()
        except RuntimeError as e:
            logger.warning(
                f"Sample {i + 1}/{num_samples}: Scan temporarily unavailable, "
                f"skipping this sample. ({e})"
            )
            if i < num_samples - 1:
                time.sleep(failure_cooldown)
            continue

        if not readings:
            logger.warning(f"Sample {i + 1}/{num_samples}: No networks found. Retrying...")
            if i < num_samples - 1:
                time.sleep(interval)
            continue

        fp = Fingerprint(
            location=location,
            readings=readings,
            timestamp=datetime.now(),
        )
        fingerprints.append(fp)

        if callback:
            callback(i, num_samples, len(readings))

        logger.debug(
            f"Sample {i + 1}/{num_samples}: Captured {len(readings)} APs at '{location}'"
        )

        if i < num_samples - 1:
            time.sleep(interval)

    logger.info(
        f"Collected {len(fingerprints)} fingerprints at location '{location}'"
    )
    return fingerprints


def build_feature_matrix(
    fingerprints: list[dict],
) -> tuple[list[list[float]], list[str], list[str]]:
    """Transform fingerprints into a feature matrix for model training.

    Each unique BSSID across all fingerprints becomes a feature column.
    Each fingerprint becomes a row with RSSI values (-100 for undetected APs).

    Args:
        fingerprints: List of fingerprint dictionaries from the database.
                      Each has keys: location, raw_data (list of reading dicts).

    Returns:
        A tuple of (feature_matrix, labels, bssid_list) where:
        - feature_matrix: 2D list of RSSI values (rows=fingerprints, cols=BSSIDs)
        - labels: Location label for each row
        - bssid_list: Ordered list of BSSIDs (column names)
    """
    # Collect all unique BSSIDs
    all_bssids: set[str] = set()
    for fp in fingerprints:
        for reading in fp["raw_data"]:
            if reading.get("bssid"):
                all_bssids.add(reading["bssid"])

    bssid_list = sorted(all_bssids)
    bssid_index = {bssid: idx for idx, bssid in enumerate(bssid_list)}

    feature_matrix: list[list[float]] = []
    labels: list[str] = []

    for fp in fingerprints:
        row = [-100.0] * len(bssid_list)
        for reading in fp["raw_data"]:
            bssid = reading.get("bssid")
            if bssid and bssid in bssid_index:
                row[bssid_index[bssid]] = float(reading["rssi"])
        feature_matrix.append(row)
        labels.append(fp["location"])

    logger.info(
        f"Built feature matrix: {len(feature_matrix)} samples, "
        f"{len(bssid_list)} features (BSSIDs), "
        f"{len(set(labels))} locations"
    )
    return feature_matrix, labels, bssid_list


def augment_fingerprints(
    fingerprints: list[dict],
    num_augmented: int = 2,
    noise_std: float = 3.0,
    seed: int | None = 42,
) -> list[dict]:
    """Generate augmented copies of fingerprints with Gaussian RSSI noise.

    Simulates the natural signal variation that occurs when a user moves
    within a room, making the trained model more robust to small positional
    changes.

    Args:
        fingerprints: Original fingerprint dicts from the database.
        num_augmented: Number of noisy copies to create per fingerprint.
        noise_std: Standard deviation (dB) of Gaussian noise added to RSSI.
            Typical indoor variation is 2–5 dB.
        seed: Random seed for reproducibility.  *None* disables seeding.

    Returns:
        A new list containing all original fingerprints **plus** the
        augmented copies.
    """
    rng = random.Random(seed)
    augmented: list[dict] = list(fingerprints)

    for fp in fingerprints:
        for _ in range(num_augmented):
            new_readings = []
            for reading in fp["raw_data"]:
                new_reading = dict(reading)
                noise = rng.gauss(0, noise_std)
                new_reading["rssi"] = max(-100.0, min(0.0, reading["rssi"] + noise))
                new_readings.append(new_reading)
            augmented.append({
                "location": fp["location"],
                "raw_data": new_readings,
                "timestamp": fp.get("timestamp", ""),
            })

    logger.info(
        f"Augmented {len(fingerprints)} fingerprints → {len(augmented)} "
        f"(+{len(augmented) - len(fingerprints)} synthetic, noise_std={noise_std} dB)"
    )
    return augmented
