"""Unergy Remote Server — WebSocket hub entry point.

Run with:
    cd remote-server
    uvicorn main:app --reload --port 8001
"""

import logging
import uuid

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.ws.manager import ConnectionManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Unergy Remote Server",
    version="0.1.0",
    description=(
        "Hub en tiempo real para la plataforma Unergy. "
        "Recibe eventos del servidor local y los retransmite "
        "a todos los clientes conectados vía WebSocket."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

manager = ConnectionManager()


@app.get("/", tags=["health"])
def health_check():
    """Health check / root endpoint."""
    return {
        "service": "Unergy Remote Server",
        "version": "0.1.0",
        "status": "running",
        "active_connections": manager.active_count,
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, client_id: str | None = None):
    """Main WebSocket endpoint.

    Clients can connect with an optional ``client_id`` query parameter:
        ws://localhost:8001/ws?client_id=user-123

    If no client_id is provided, a random UUID is assigned.

    Supported inbound event types:
    - ``location_change``: User moved to a different space
    - ``space_registered``: New space was registered
    - ``ping``: Keep-alive

    All received events are broadcast to other connected clients.
    """
    cid = client_id or str(uuid.uuid4())
    await manager.connect(websocket, cid)

    try:
        while True:
            data = await websocket.receive_json()

            event_type = data.get("type", "unknown")
            logger.info(f"Event from {cid}: {event_type}")

            # Enrich event with sender info before broadcasting
            outbound = {
                "sender": cid,
                "type": event_type,
                "payload": data.get("payload", {}),
            }
            await manager.broadcast(outbound, exclude=cid)
    except WebSocketDisconnect:
        manager.disconnect(cid)
        await manager.broadcast(
            {"type": "client_disconnected", "sender": "server", "payload": {"client_id": cid}}
        )
