"""Tests for the remote WebSocket hub."""

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestHealth:
    def test_health_check(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "running"
        assert body["active_connections"] == 0


class TestWebSocket:
    def test_connect_and_receive_broadcast(self, client):
        """Two clients connect; when one sends, the other receives."""
        with client.websocket_connect("/ws?client_id=user-1") as ws1:
            with client.websocket_connect("/ws?client_id=user-2") as ws2:
                ws2.send_json({
                    "type": "space_registered",
                    "payload": {"space_name": "Cocina"},
                })
                msg = ws1.receive_json()
                assert msg["type"] == "space_registered"
                assert msg["sender"] == "user-2"
                assert msg["payload"]["space_name"] == "Cocina"

    def test_sender_does_not_receive_own_message(self, client):
        """A client that sends an event should not receive it back."""
        with client.websocket_connect("/ws?client_id=user-a") as ws_a:
            with client.websocket_connect("/ws?client_id=user-b") as ws_b:
                ws_a.send_json({
                    "type": "location_change",
                    "payload": {"from": "Sala", "to": "Cocina"},
                })
                # user-b should receive the broadcast
                msg = ws_b.receive_json()
                assert msg["type"] == "location_change"
                assert msg["sender"] == "user-a"

    def test_auto_assigned_client_id(self, client):
        """When no client_id is provided, the server assigns one."""
        with client.websocket_connect("/ws") as ws1:
            with client.websocket_connect("/ws?client_id=sender") as ws2:
                ws2.send_json({
                    "type": "ping",
                    "payload": {},
                })
                msg = ws1.receive_json()
                assert msg["sender"] == "sender"
                assert msg["type"] == "ping"
