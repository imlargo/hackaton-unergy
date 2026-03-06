"""Model training logic for WiFi fingerprint-based indoor positioning."""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.model_selection import cross_val_score
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder, StandardScaler

from wifipos.model.fingerprint import build_feature_matrix
from wifipos.storage.database import Database

logger = logging.getLogger(__name__)


@dataclass
class TrainingResult:
    """Result of model training."""

    accuracy: float
    cv_scores: list[float]
    locations: list[str]
    feature_count: int
    sample_count: int
    classifier_name: str
    comparison_results: dict[str, float]


def train_model(db: Database) -> TrainingResult:
    """Train a WiFi positioning model using stored fingerprints.

    Trains a RandomForest classifier by default and compares with KNN
    and GradientBoosting. Uses 5-fold cross-validation.

    Args:
        db: The database containing fingerprints.

    Returns:
        A TrainingResult with accuracy metrics and model info.

    Raises:
        ValueError: If there aren't enough locations or fingerprints.
    """
    fingerprints = db.get_all_fingerprints()
    counts = db.get_fingerprint_count_by_location()

    # Validate minimum requirements
    if len(counts) < 2:
        raise ValueError(
            f"At least 2 locations are required for training, but only "
            f"{len(counts)} found. Use 'wifipos learn <location>' to add more locations."
        )

    for location, count in counts.items():
        if count < 3:
            raise ValueError(
                f"Location '{location}' has only {count} fingerprints. "
                f"At least 3 are required per location. "
                f"Use 'wifipos learn {location}' to collect more samples."
            )

    # Build feature matrix
    X_list, y_list, bssid_list = build_feature_matrix(fingerprints)
    X = np.array(X_list)
    y_raw = np.array(y_list)

    # Encode labels
    label_encoder = LabelEncoder()
    y = label_encoder.fit_transform(y_raw)

    locations = list(label_encoder.classes_)
    logger.info(f"Training with {len(X)} samples, {len(bssid_list)} features, {len(locations)} locations")

    # Warn about low sample counts
    for location, count in counts.items():
        if count < 5:
            logger.warning(
                f"Location '{location}' has only {count} fingerprints. "
                f"Consider collecting more for better accuracy."
            )

    # Define classifiers to evaluate
    classifiers = {
        "RandomForest": RandomForestClassifier(n_estimators=150, random_state=42),
        "KNN": KNeighborsClassifier(n_neighbors=min(5, len(X) - 1)),
        "GradientBoosting": GradientBoostingClassifier(n_estimators=100, random_state=42),
    }

    comparison_results: dict[str, float] = {}
    n_folds = min(5, min(counts.values()))

    for name, clf in classifiers.items():
        pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("classifier", clf),
        ])
        try:
            scores = cross_val_score(pipeline, X, y, cv=n_folds, scoring="accuracy")
            comparison_results[name] = float(np.mean(scores))
            logger.info(f"{name}: CV accuracy = {np.mean(scores):.4f} (+/- {np.std(scores):.4f})")
        except Exception as e:
            logger.warning(f"Failed to evaluate {name}: {e}")
            comparison_results[name] = 0.0

    # Train the default RandomForest model
    best_pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("classifier", RandomForestClassifier(n_estimators=150, random_state=42)),
    ])
    best_pipeline.fit(X, y)

    # Get final CV scores for the selected model
    cv_scores = cross_val_score(best_pipeline, X, y, cv=n_folds, scoring="accuracy")

    # Serialize the model
    model_data = {
        "pipeline": best_pipeline,
        "bssid_list": bssid_list,
        "label_encoder": label_encoder,
    }
    buffer = io.BytesIO()
    joblib.dump(model_data, buffer)
    model_blob = buffer.getvalue()

    # Metadata for the database
    metadata = {
        "accuracy": float(np.mean(cv_scores)),
        "cv_scores": [float(s) for s in cv_scores],
        "locations": locations,
        "feature_count": len(bssid_list),
        "sample_count": len(X),
        "classifier": "RandomForest",
        "comparison": comparison_results,
    }

    db.save_model(model_blob, metadata)

    return TrainingResult(
        accuracy=float(np.mean(cv_scores)),
        cv_scores=[float(s) for s in cv_scores],
        locations=locations,
        feature_count=len(bssid_list),
        sample_count=len(X),
        classifier_name="RandomForest",
        comparison_results=comparison_results,
    )
