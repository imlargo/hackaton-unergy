"""Space management service."""

from __future__ import annotations

import logging
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

    def register_space(self, user_id: int, data: SpaceCreate) -> SpaceResponse:
        """Register a new space using current WiFi environment data.

        This performs the full wifipos workflow:
        1. Scan WiFi networks in the current environment.
        2. Save the space with WiFi metadata.
        3. Save the scan as a fingerprint in the wifipos database.
        4. Attempt to retrain the positioning model.
        """
        wifi_metadata = self._wifi_service.scan_current_environment()

        space = self._space_repo.create(
            user_id=user_id,
            name=data.name,
            space_type=data.space_type,
            wifi_metadata=wifi_metadata,
        )

        # Save fingerprint to wifipos database (like `wifipos learn`)
        self._wifi_service.save_fingerprint(data.name, wifi_metadata)

        # Auto-train model if enough data (like `wifipos train`)
        training_result = self._wifi_service.try_train_model()
        if training_result:
            logger.info(
                "Model auto-trained after registering '%s': accuracy=%.2f",
                data.name,
                training_result["accuracy"],
            )

        logger.info(
            f"Space '{space.name}' registered for user {user_id} "
            f"with {wifi_metadata.get('networks_detected', 0)} networks"
        )
        return self._to_response(space)

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

    @staticmethod
    def _to_response(space: Space) -> SpaceResponse:
        return SpaceResponse(
            id=space.id,
            user_id=space.user_id,
            name=space.name,
            space_type=space.space_type,
            wifi_metadata=space.wifi_metadata,
            created_at=space.created_at,
        )
