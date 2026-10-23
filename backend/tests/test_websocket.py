"""Testes de integração do endpoint WebSocket (/ws/races/{race_id})."""

import json

import pytest

try:
    from fastapi.testclient import TestClient

    from app.main import app

    HAS_FASTAPI = True
except ModuleNotFoundError:
    HAS_FASTAPI = False


@pytest.mark.skipif(
    not HAS_FASTAPI, reason="FastAPI / TestClient não instalado no ambiente local (use Docker/uv)"
)
def test_websocket_connection_and_initial_envelope():
    """Valida a conexão WebSocket e o recebimento do envelope inicial lap_update."""
    client = TestClient(app)
    with client.websocket_connect("/ws/races/test-race-ws") as websocket:
        data = websocket.receive_text()
        envelope = json.loads(data)

        assert envelope["type"] == "lap_update"
        assert envelope["race_id"] == "test-race-ws"
        assert envelope["current_lap"] == 0
        assert len(envelope["drivers"]) == 20

        # Envia comandos de controle
        websocket.send_text(json.dumps({"action": "pause"}))
        websocket.send_text(json.dumps({"action": "set_speed", "speed_multiplier": 2.0}))
        websocket.send_text(json.dumps({"action": "resume"}))
