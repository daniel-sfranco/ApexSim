"""
Handler WebSocket para transmissão de telemetria e recepção de comandos (Contrato D2).
=====================================================================================

Ponte de transporte entre clientes web (Cockpit / Timing Tower) e o motor `RaceEngine`.
Gerencia conexões, despacho de mensagens `lap_update` e encaminhamento de comandos
`play`, `pause`, `resume`, `set_speed` e `restart`.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from sim.engine import RaceEngine
from sim.run import montar_grid_inicial
from sim.state import RaceState
from sim.track import TrackMap

logger = logging.getLogger("apexsim.websocket")

router = APIRouter()

active_engines: dict[str, RaceEngine] = {}
active_tasks: dict[str, asyncio.Task[None]] = {}
connected_clients: dict[str, set[WebSocket]] = {}


def get_or_create_engine(
    race_id: str,
    state: RaceState | None = None,
    seed: int = 42,
    weather: str = "DRY",
    track_temp: float = 32.0,
    force_new: bool = False,
    circuit_id: str = "interlagos",
) -> RaceEngine:
    """Recupera a instância ativa do RaceEngine ou inicializa uma nova para a corrida."""
    if force_new and race_id in active_engines:
        active_engines[race_id].stop()
        if race_id in active_tasks:
            active_tasks[race_id].cancel()

    if race_id not in active_engines or force_new:
        initial_state = state or montar_grid_inicial()

        track_map = None
        try:
            track_map = TrackMap.load(circuit_id)
        except Exception as e:
            logger.warning(f"Não foi possível carregar TrackMap para '{circuit_id}': {e}")

        async def _broadcast(envelope: dict[str, Any]) -> None:
            clients = connected_clients.get(race_id, set()).copy()
            if not clients:
                return
            message = json.dumps(envelope)
            for ws in clients:
                try:
                    await ws.send_text(message)
                except Exception:
                    # Desconexões tratadas no handler principal
                    pass

        engine = RaceEngine(
            race_state=initial_state,
            race_id=race_id,
            seed=seed,
            weather=weather,
            track_temp=track_temp,
            broadcast_fn=_broadcast,
            track_map=track_map,
        )
        active_engines[race_id] = engine
        active_tasks[race_id] = asyncio.create_task(engine.run())

    return active_engines[race_id]


async def _handle_connection(websocket: WebSocket, race_id: str) -> None:
    await websocket.accept()
    connected_clients.setdefault(race_id, set()).add(websocket)

    engine = get_or_create_engine(race_id)

    # Envia snapshot da volta atual imediatamente após conectar
    try:
        await websocket.send_text(json.dumps(engine.get_lap_update_envelope()))
    except Exception as e:
        logger.warning(f"Erro ao enviar snapshot inicial para {race_id}: {e}")

    try:
        while True:
            raw_text = await websocket.receive_text()
            try:
                payload = json.loads(raw_text)
                if not isinstance(payload, dict):
                    continue

                action = payload.get("action")
                if action in ("restart", "start", "init"):
                    new_state = montar_grid_inicial()
                    total_laps = payload.get("total_laps") or payload.get("totalLaps")
                    if total_laps:
                        new_state.total_laps = int(total_laps)

                    circuit_id = (
                        payload.get("circuit_id")
                        or payload.get("circuitId")
                        or "interlagos"
                    )
                    engine = get_or_create_engine(
                        race_id=race_id,
                        state=new_state,
                        seed=payload.get("seed", 42),
                        weather=payload.get("weather", "DRY"),
                        force_new=True,
                        circuit_id=circuit_id,
                    )
                    await websocket.send_text(json.dumps(engine.get_lap_update_envelope()))
                else:
                    engine.handle_command(payload)
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        logger.info(f"Cliente WebSocket desconectado da corrida {race_id}")
    finally:
        if race_id in connected_clients:
            connected_clients[race_id].discard(websocket)
            if not connected_clients[race_id]:
                connected_clients.pop(race_id, None)


@router.websocket("/ws/races/{race_id}")
async def race_websocket_endpoint(websocket: WebSocket, race_id: str) -> None:
    """Endpoint oficial para conexão WebSocket por identificador de corrida."""
    await _handle_connection(websocket, race_id)


@router.websocket("/ws")
@router.websocket("/ws/")
async def generic_websocket_endpoint(websocket: WebSocket) -> None:
    """Endpoint genérico para clientes sem race_id explícito na URL."""
    await _handle_connection(websocket, "default")
