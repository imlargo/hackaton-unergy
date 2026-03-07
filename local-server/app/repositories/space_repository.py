"""Persistent JSON-file space repository.

Spaces are stored in a JSON file on disk so they survive server
restarts.  The file path defaults to ``data/spaces.json`` relative
to the local-server working directory (configurable via constructor).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from app.domain.space import Space

logger = logging.getLogger(__name__)

# Path: repositories/ → app/ → local-server/ → data/spaces.json
_DEFAULT_DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "spaces.json"


class SpaceRepository:
    """JSON-file-backed space storage.

    Public interface is identical to the original in-memory version
    so all existing callers (SpaceService, tests) work without changes.
    """

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path else _DEFAULT_DATA_PATH
        self._spaces: dict[int, dict] = {}
        self._next_id: int = 1
        self._load()

    # ------------------------------------------------------------------
    # Public API (same interface as the old in-memory version)
    # ------------------------------------------------------------------

    def create(
        self,
        user_id: int,
        name: str,
        space_type: str,
        wifi_metadata: dict[str, Any] | None = None,
    ) -> Space:
        """Create, persist and return a new space."""
        space_data = {
            "id": self._next_id,
            "user_id": user_id,
            "name": name,
            "space_type": space_type,
            "wifi_metadata": wifi_metadata or {},
            "created_at": datetime.now().isoformat(),
        }
        self._spaces[self._next_id] = space_data
        self._next_id += 1
        self._save()
        return self._to_space(space_data)

    def get_by_id(self, space_id: int) -> Space | None:
        """Retrieve a space by ID."""
        data = self._spaces.get(space_id)
        if data is None:
            return None
        return self._to_space(data)

    def list_by_user(self, user_id: int) -> list[Space]:
        """List all spaces belonging to a user."""
        return [
            self._to_space(data)
            for data in self._spaces.values()
            if data["user_id"] == user_id
        ]

    def delete(self, space_id: int) -> bool:
        """Delete a space by ID.  Returns True if deleted."""
        removed = self._spaces.pop(space_id, None) is not None
        if removed:
            self._save()
        return removed

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load spaces from the JSON file (if it exists)."""
        if not self._path.exists():
            logger.info("No existing spaces file at %s — starting fresh.", self._path)
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            self._spaces = {int(k): v for k, v in raw.get("spaces", {}).items()}
            self._next_id = raw.get("next_id", 1)
            logger.info(
                "Loaded %d space(s) from %s", len(self._spaces), self._path
            )
        except Exception as exc:
            logger.error("Failed to load spaces from %s: %s", self._path, exc)

    def _save(self) -> None:
        """Write current state to the JSON file."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "next_id": self._next_id,
            "spaces": {str(k): v for k, v in self._spaces.items()},
        }
        self._path.write_text(
            json.dumps(payload, indent=2, default=str, ensure_ascii=False),
            encoding="utf-8",
        )

    @staticmethod
    def _to_space(data: dict) -> Space:
        """Convert a raw dict to a Space model."""
        created = data["created_at"]
        if isinstance(created, str):
            created = datetime.fromisoformat(created)
        return Space(
            id=data["id"],
            user_id=data["user_id"],
            name=data["name"],
            space_type=data["space_type"],
            wifi_metadata=data.get("wifi_metadata", {}),
            created_at=created,
        )
