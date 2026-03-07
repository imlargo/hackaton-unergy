"""Space management service."""

from __future__ import annotations

import logging
import threading
from typing import Any

from fastapi import HTTPException, status

from app.domain.space import Space, SpaceCreate, SpaceResponse
from app.repositories.space_repository import SpaceRepository
from app.services.wifi_integration_service import WiFiIntegrationService

logger = logging.getLogger(__name__)


class SpaceService:
    """Handles space registration and retrieval logic."""

    def __init__(
        self,
        space_repo: SpaceRepository,
        wifi_service: WiFiIntegrationService,
    ) -> None:
        self._space_repo = space_repo
        self._wifi_service = wifi_service
        # Track background collection status per space name
        self._collection_status: dict[str, dict[str, Any]] = {}
        self._collection_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Collection status helpers
    # ------------------------------------------------------------------

    def _set_collection_status(self, space_name: str, status_data: dict[str, Any]) -> None:
        with self._collection_lock:
            self._collection_status[space_name] = status_data

    def get_collection_status(self, space_name: str) -> dict[str, Any] | None:
        """Return the background collection status for a space, if any."""
        with self._collection_lock:
            return self._collection_status.get(space_name)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_space(self, user_id: int, data: SpaceCreate) -> SpaceResponse:
        """Register a new space — returns immediately.

        Performs a quick single WiFi scan for metadata, saves the space,
        then kicks off fingerprint collection in the background so the
        HTTP response is not blocked.
        """
        logger.info(
            "▶ Registering space '%s' (type=%s, samples=%d) for user %d …",
            data.name, data.space_type, data.samples, user_id,
        )

        # 1. Quick single scan for space metadata
        wifi_metadata = self._wifi_service.scan_current_environment()
        logger.info(
            "  WiFi scan done: %d networks detected (source=%s).",
            wifi_metadata.get("networks_detected", 0),
            wifi_metadata.get("source", "unknown"),
        )

        # 2. Save space immediately
        space = self._space_repo.create(
            user_id=user_id,
            name=data.name,
            space_type=data.space_type,
            wifi_metadata=wifi_metadata,
        )
        logger.info("  Space '%s' saved with id=%d.", space.name, space.id)

        # 3. Save one initial fingerprint synchronously (fast)
        saved_initial = self._wifi_service.save_fingerprint(data.name, wifi_metadata)
        logger.info(
            "  Initial fingerprint saved: %s", "OK" if saved_initial else "SKIPPED",
        )

        # 4. Mark background collection as pending
        self._set_collection_status(data.name, {
            "status": "collecting",
            "samples_requested": data.samples,
            "fingerprints_saved": 1 if saved_initial else 0,
            "model_trained": False,
        })

        # Build immediate feedback
        feedback: dict[str, Any] = {
            "fingerprints_saved": 1 if saved_initial else 0,
            "samples_requested": data.samples,
            "wifi_source": wifi_metadata.get("source", "unknown"),
            "networks_detected": wifi_metadata.get("networks_detected", 0),
            "collection_status": "collecting",
            "model_trained": False,
            "model_note": (
                f"Collecting {data.samples} WiFi samples in background "
                "(walk around the space!). Model trains automatically "
                "when ≥2 locations have ≥3 fingerprints."
            ),
        }

        logger.info(
            "✔ Space '%s' registered — returning immediately. "
            "Background collection of %d samples starting now.",
            space.name, data.samples,
        )
        return self._to_response(space, feedback=feedback)

    def run_background_collection(self, space_name: str, num_samples: int) -> None:
        """Run walk-mode fingerprint collection + auto-train (called in background).

        This is the heavy part that used to block the HTTP request.
        Now it runs in a background thread / FastAPI BackgroundTask.
        """
        logger.info(
            "🔄 [background] Starting walk-mode collection for '%s' "
            "(%d samples, 2s interval) …",
            space_name, num_samples,
        )

        def _on_progress(saved: int, total: int) -> None:
            """Update the collection status dict after each fingerprint."""
            self._set_collection_status(space_name, {
                "status": "collecting",
                "samples_requested": total,
                "fingerprints_saved": saved,
                "model_trained": False,
            })

        try:
            collection = self._wifi_service.collect_and_save_fingerprints(
                location=space_name,
                num_samples=num_samples,
                interval=2.0,
                progress_callback=_on_progress,
            )
            logger.info(
                "🔄 [background] Collection done for '%s': %d/%d fingerprints saved.",
                space_name,
                collection["fingerprints_saved"],
                collection["samples_requested"],
            )

            # Auto-train model if enough data
            training_result = self._wifi_service.try_train_model()
            if training_result:
                logger.info(
                    "🎯 [background] Model auto-trained after '%s': "
                    "accuracy=%.2f, locations=%s",
                    space_name,
                    training_result["accuracy"],
                    training_result["locations"],
                )

            self._set_collection_status(space_name, {
                "status": "done",
                "samples_requested": num_samples,
                "fingerprints_saved": collection["fingerprints_saved"],
                "model_trained": training_result is not None,
                "model_accuracy": training_result["accuracy"] if training_result else None,
            })
            logger.info("✅ [background] '%s' fully processed.", space_name)

        except Exception as exc:
            logger.error(
                "❌ [background] Collection failed for '%s': %s", space_name, exc,
            )
            self._set_collection_status(space_name, {
                "status": "error",
                "error": str(exc),
            })

    def list_spaces(self, user_id: int) -> list[SpaceResponse]:
        """List all spaces belonging to a user."""
        spaces = self._space_repo.list_by_user(user_id)
        return [self._to_response(s) for s in spaces]

    def get_space(self, space_id: int, user_id: int) -> SpaceResponse:
        """Get a single space by ID, ensuring it belongs to the user."""
        space = self._space_repo.get_by_id(space_id)
        if space is None or space.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Space not found",
            )
        return self._to_response(space)

    def reset_all(self) -> dict[str, Any]:
        """Delete all spaces, fingerprints, and trained models."""
        spaces_deleted = self._space_repo.delete_all()
        wifi_reset = self._wifi_service.reset_wifi_data()
        logger.info(
            "Full reset: %d spaces deleted, wifi data reset.",
            spaces_deleted,
        )
        return {
            "spaces_deleted": spaces_deleted,
            "wifi_reset": wifi_reset,
        }

    @staticmethod
    def _to_response(space: Space, feedback: dict[str, Any] | None = None) -> SpaceResponse:
        return SpaceResponse(
            id=space.id,
            user_id=space.user_id,
            name=space.name,
            space_type=space.space_type,
            wifi_metadata=space.wifi_metadata,
            created_at=space.created_at,
            registration_feedback=feedback,
        )
