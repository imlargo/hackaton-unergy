"""Real-time prediction using a trained WiFi positioning model."""

from __future__ import annotations

import io
import logging
import time
from dataclasses import dataclass
from typing import Callable

import joblib
import numpy as np

from wifipos.scanner.base import WifiScanner
from wifipos.storage.database import Database

logger = logging.getLogger(__name__)


@dataclass
class Prediction:
    """A location prediction result."""

    location: str
    confidence: float
    probabilities: dict[str, float]

    def __str__(self) -> str:
        probs = ", ".join(f"{k}: {v:.1%}" for k, v in sorted(self.probabilities.items(), key=lambda x: -x[1]))
        return f"Predicted: {self.location} ({self.confidence:.1%}) [{probs}]"


class Predictor:
    """Performs location predictions using a trained model."""

    def __init__(self, db: Database) -> None:
        """Initialize the predictor by loading the latest model.

        Args:
            db: The database containing trained models.

        Raises:
            ValueError: If no trained model is found.
        """
        model_row = db.load_latest_model()
        if model_row is None:
            raise ValueError(
                "No trained model found. Run 'wifipos train' first."
            )

        model_data = joblib.load(io.BytesIO(model_row["model_blob"]))
        self._pipeline = model_data["pipeline"]
        self._bssid_list: list[str] = model_data["bssid_list"]
        self._label_encoder = model_data["label_encoder"]
        self._metadata = model_row["metadata"]

        logger.info(
            f"Loaded model trained on {self._metadata.get('sample_count', '?')} samples "
            f"with {len(self._bssid_list)} features"
        )

    def predict(self, scanner: WifiScanner) -> Prediction:
        """Perform a single location prediction.

        Args:
            scanner: The WiFi scanner to use for the current scan.

        Returns:
            A Prediction with the most likely location and probabilities.
        """
        readings = scanner.scan()

        if not readings:
            logger.warning("No WiFi networks detected. Prediction may be unreliable.")

        # Build feature vector matching training BSSIDs
        bssid_index = {bssid: idx for idx, bssid in enumerate(self._bssid_list)}
        feature_vector = [-100.0] * len(self._bssid_list)

        for reading in readings:
            if reading.bssid in bssid_index:
                feature_vector[bssid_index[reading.bssid]] = float(reading.rssi)

        X = np.array([feature_vector])

        # Predict
        predicted_label = self._pipeline.predict(X)[0]
        location = self._label_encoder.inverse_transform([predicted_label])[0]

        # Get probabilities
        probas = self._pipeline.predict_proba(X)[0]
        prob_dict = {
            self._label_encoder.inverse_transform([i])[0]: float(p)
            for i, p in enumerate(probas)
        }
        confidence = float(max(probas))

        prediction = Prediction(
            location=location,
            confidence=confidence,
            probabilities=prob_dict,
        )
        logger.info(f"Prediction: {prediction}")
        return prediction

    def predict_continuous(
        self,
        scanner: WifiScanner,
        interval: float = 3.0,
        callback: Callable[[Prediction], None] | None = None,
    ) -> None:
        """Continuously predict location in a loop.

        Args:
            scanner: The WiFi scanner to use.
            interval: Seconds between predictions.
            callback: Optional callback(prediction) called after each prediction.
        """
        logger.info(f"Starting continuous prediction (interval={interval}s). Press Ctrl+C to stop.")
        try:
            while True:
                try:
                    prediction = self.predict(scanner)
                    if callback:
                        callback(prediction)
                except Exception as e:
                    logger.error(f"Prediction error: {e}")
                time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("Continuous prediction stopped.")
