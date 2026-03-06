"""WebSocket connection manager for the remote hub."""

from __future__ import annotations

import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts events.

    Designed to support multiple concurrent users. Each connection
    can be identified by an optional ``client_id``.
    """

    def __init__(self) -> None:
        self._active: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, client_id: str) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self._active[client_id] = websocket
        logger.info(f"Client connected: {client_id} (total: {len(self._active)})")

    def disconnect(self, client_id: str) -> None:
        """Remove a connection from the active set."""
        self._active.pop(client_id, None)
        logger.info(f"Client disconnected: {client_id} (total: {len(self._active)})")

    async def send_personal(self, message: dict, client_id: str) -> None:
        """Send a message to a specific client."""
        ws = self._active.get(client_id)
        if ws:
            await ws.send_json(message)

    async def broadcast(self, message: dict, exclude: str | None = None) -> None:
        """Broadcast a message to all connected clients.

        Args:
            message: JSON-serializable dict to send.
            exclude: Optional client_id to exclude from broadcast.
        """
        disconnected: list[str] = []
        for cid, ws in self._active.items():
            if cid == exclude:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(cid)
        for cid in disconnected:
            self.disconnect(cid)

    @property
    def active_count(self) -> int:
        return len(self._active)

    @property
    def active_clients(self) -> list[str]:
        return list(self._active.keys())
