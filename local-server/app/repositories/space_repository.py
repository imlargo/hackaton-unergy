"""Mock in-memory space repository.

This repository stores spaces in memory for MVP validation.
To migrate to a real database later, replace this class with an
implementation backed by a real persistence layer, keeping the
same public interface.
"""

from datetime import datetime
from typing import Any

from app.domain.space import Space


class SpaceRepository:
    """In-memory space storage."""

    def __init__(self) -> None:
        self._spaces: dict[int, dict] = {}
        self._next_id: int = 1

    def create(
        self,
        user_id: int,
        name: str,
        space_type: str,
        wifi_metadata: dict[str, Any] | None = None,
    ) -> Space:
        """Create and store a new space."""
        space_data = {
            "id": self._next_id,
            "user_id": user_id,
            "name": name,
            "space_type": space_type,
            "wifi_metadata": wifi_metadata or {},
            "created_at": datetime.now(),
        }
        self._spaces[self._next_id] = space_data
        self._next_id += 1
        return Space(**space_data)

    def get_by_id(self, space_id: int) -> Space | None:
        """Retrieve a space by ID."""
        data = self._spaces.get(space_id)
        if data is None:
            return None
        return Space(**data)

    def list_by_user(self, user_id: int) -> list[Space]:
        """List all spaces belonging to a user."""
        return [
            Space(**data)
            for data in self._spaces.values()
            if data["user_id"] == user_id
        ]

    def delete(self, space_id: int) -> bool:
        """Delete a space by ID. Returns True if deleted."""
        return self._spaces.pop(space_id, None) is not None
