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
import uuid
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.db_sessao import engine as db_engine
from app.models.track import TrackMap
from app.persistencia import GravadorDeCorrida
from db.repositorio import carregar_corrida
from sim.engine import RaceEngine
from sim.run import montar_grid_inicial
from sim.state import DriverState, PitStatus, RaceState, TrackStatus, TyreCompound

logger = logging.getLogger("apexsim.websocket")

router = APIRouter()

active_engines: dict[str, RaceEngine] = {}
active_tasks: dict[str, asyncio.Task[None]] = {}
connected_clients: dict[str, set[WebSocket]] = {}


def _montar_estado_da_corrida_do_banco(
    race_id_str: str,
) -> tuple[RaceState | None, float, int, str, float]:
    """Tenta carregar os dados de corrida configurados previamente no banco."""
    try:
        race_uuid = uuid.UUID(race_id_str)
        with Session(db_engine()) as session:
            carregada = carregar_corrida(session, race_uuid)
            track_length = 4309.0
            try:
                tm = TrackMap.load(carregada.circuit_id)
                track_length = float(tm.length_m)
            except Exception:
                pass

            drivers = {}
            for entry in carregada.grid:
                initial_tyre_str = (carregada.config.get("initial_tyres") or {}).get(
                    entry.code, "MEDIUM"
                )
                try:
                    tyre_enum = TyreCompound[initial_tyre_str]
                except Exception:
                    tyre_enum = TyreCompound.MEDIUM

                drivers[entry.code] = DriverState(
                    driver_id=entry.code,
                    name=entry.name,
                    team=entry.team,
                    position=entry.grid_position,
                    lap_distance_covered=0.0,
                    total_distance_covered=0.0,
                    current_lap=0,
                    last_lap_time=None,
                    gap_to_leader=(
                        0.0
                        if entry.grid_position == 1
                        else float(entry.grid_position - 1) * 0.3
                    ),
                    gap_to_ahead=None if entry.grid_position == 1 else 0.3,
                    tyre_compound=tyre_enum,
                    tyre_age=0,
                    fuel_load=110.0,
                    pit_status=PitStatus.NONE,
                    pit_stops_made=0,
                    is_retired=False,
                    base_velocity=20.0,
                    lap_time_sum=0.0,
                    drs_active=False,
                )

            state = RaceState(
                current_lap=0,
                total_laps=carregada.total_laps,
                track_status=TrackStatus.GREEN,
                drivers=drivers,
                lap_history=[],
                elapsed_time=0.0,
                is_finished=False,
            )
            weather = carregada.config.get("weather", "DRY")
            track_temp = float(carregada.config.get("track_temp", 32.0))
            return state, track_length, carregada.seed, weather, track_temp
    except Exception as e:
        logger.debug(f"Não foi possível carregar corrida do banco ({race_id_str}): {e}")
        return None, 4309.0, 42, "DRY", 32.0


def get_or_create_engine(
    race_id: str,
    state: RaceState | None = None,
    seed: int = 42,
    weather: str = "DRY",
    track_temp: float = 32.0,
    force_new: bool = False,
) -> RaceEngine:
    """Recupera a instância ativa do RaceEngine ou inicializa uma nova para a corrida."""
    if force_new and race_id in active_engines:
        active_engines[race_id].stop()
        if race_id in active_tasks:
            active_tasks[race_id].cancel()

    if race_id not in active_engines or force_new:
        track_length = 4309.0
        initial_state = state
        if initial_state is None:
            (
                db_state,
                db_track_len,
                db_seed,
                db_weather,
                db_track_temp,
            ) = _montar_estado_da_corrida_do_banco(race_id)
            if db_state is not None:
                initial_state = db_state
                track_length = db_track_len
                seed = db_seed
                weather = db_weather
                track_temp = db_track_temp
            else:
                initial_state = montar_grid_inicial()

        gravador: GravadorDeCorrida | None = None
        try:
            race_uuid = uuid.UUID(race_id)
            gravador = GravadorDeCorrida(db_engine(), race_uuid)
            asyncio.create_task(gravador.mudar_status("running"))
        except Exception:
            gravador = None

        async def _broadcast(envelope: dict[str, Any]) -> None:
            if gravador and envelope.get("type") == "lap_update":
                try:
                    c_lap = envelope.get("current_lap")
                    voltas_da_volta = [
                        v for v in engine.state.lap_history if v.lap_number == c_lap
                    ]
                    if voltas_da_volta:
                        await gravador.registrar_volta(voltas_da_volta)
                    if engine.state.is_finished:
                        await gravador.mudar_status("finished")
                except Exception as err:
                    logger.debug(f"Aviso ao persistir volta no banco: {err}")

            clients = connected_clients.get(race_id, set()).copy()
            if not clients:
                return
            message = json.dumps(envelope)
            for ws in clients:
                try:
                    await ws.send_text(message)
                except Exception:
                    pass

        engine = RaceEngine(
            race_state=initial_state,
            track_length=track_length,
            race_id=race_id,
            seed=seed,
            weather=weather,
            track_temp=track_temp,
            broadcast_fn=_broadcast,
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

                    engine = get_or_create_engine(
                        race_id=race_id,
                        state=new_state,
                        seed=payload.get("seed", 42),
                        weather=payload.get("weather", "DRY"),
                        force_new=True,
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
