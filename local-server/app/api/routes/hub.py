"""Hub API routes — lightweight in-memory presence for multi-device location sharing.

Each device identifies itself with a UUID (no auth). Devices send heartbeats
with their current location; stale entries are automatically purged.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter(prefix="/hub", tags=["hub"])

# ---------------------------------------------------------------------------
# In-memory presence store  {device_id: {...}}
# ---------------------------------------------------------------------------
_presence: dict[str, dict[str, Any]] = {}

HEARTBEAT_TIMEOUT_SECONDS = 30  # drop entries older than this


class HeartbeatPayload(BaseModel):
    device_id: str
    display_name: str = "Anónimo"
    location: str | None = None
    confidence: float = 0.0
    space_type: str | None = None


def _purge_stale() -> None:
    """Remove entries that haven't sent a heartbeat recently."""
    now = time.time()
    stale_keys = [k for k, v in _presence.items() if now - v["last_seen"] > HEARTBEAT_TIMEOUT_SECONDS]
    for k in stale_keys:
        del _presence[k]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/heartbeat")
def heartbeat(payload: HeartbeatPayload):
    """Report current location for a device. Call every few seconds."""
    _presence[payload.device_id] = {
        "device_id": payload.device_id,
        "display_name": payload.display_name,
        "location": payload.location,
        "confidence": payload.confidence,
        "space_type": payload.space_type,
        "last_seen": time.time(),
    }
    _purge_stale()
    return {"status": "ok"}


@router.get("/users")
def list_users():
    """Return all active device locations."""
    _purge_stale()
    return {
        "users": list(_presence.values()),
    }


@router.delete("/leave")
def leave(device_id: str = Query(...)):
    """Remove a device from the hub."""
    _presence.pop(device_id, None)
    return {"status": "ok"}
