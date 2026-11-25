"""
Handler WebSocket para transmissão de telemetria e recepção de comandos (Contrato D2).
=====================================================================================

Ponte de transporte entre clientes web (Cockpit / Timing Tower) e o motor `RaceEngine`.
Gerencia conexões, despacho de mensagens `lap_update` e encaminhamento de comandos
`play`, `pause`, `resume`, `set_speed` e `restart`.

Corridas gravadas no banco
--------------------------
Quando o `race_id` é o UUID de uma corrida criada por `POST /api/races`, o motor é
montado com o que está no banco (`app.corrida_persistida`) e cada volta fechada é
gravada pelo `GravadorDeCorrida` (`app.persistencia`). Ciclo de vida no banco:

- motor criado (conexão ou `restart`): histórico anterior apagado, status `running`;
- fim normal da corrida: status `finished`;
- último cliente sai antes do fim: status `aborted` (as voltas gravadas ficam).

Qualquer outro `race_id` roda só em memória, como antes.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app import db_sessao
from app.db_sessao import engine as db_engine
from app.models.track import TrackMap
from app.persistencia import GravadorDeCorrida, eventos_do_motor
from app.corrida_persistida import carregar_corrida_do_banco, estado_inicial
from db.repositorio import carregar_corrida
from sim.state import DriverState, PitStatus, RaceState, TrackStatus, TyreCompound, LapResult
from sim.engine import RaceEngine
from sim.run import montar_grid_inicial
from sim.track import TrackMap

logger = logging.getLogger("apexsim.websocket")

router = APIRouter()

active_engines: dict[str, RaceEngine] = {}
active_tasks: dict[str, asyncio.Task[None]] = {}
connected_clients: dict[str, set[WebSocket]] = {}
# Geração monotônica por corrida: garante que apenas o motor ATUAL de um
# `race_id` consiga transmitir. Uma instância antiga (cancelada em um
# "restart") nunca envia um envelope atrasado para os clientes da nova corrida.
engine_generations: dict[str, int] = {}
_generation_counter = itertools.count(1)
# Gravador da corrida em andamento (só para corridas que existem no banco).
active_recorders: dict[str, GravadorDeCorrida] = {}
# Gravação do status `aborted` ainda em voo. Quem recriar o motor da mesma corrida
# espera ela terminar, senão o `aborted` poderia chegar depois do novo `running`.
_pending_aborts: dict[str, asyncio.Task[None]] = {}
# Corridas cujo motor já foi configurado por um `init`/`start`/`restart` do cliente
# ou carregado do banco. Diferencia o motor "placeholder" criado na conexão (só
# para enviar o snapshot inicial) de uma corrida realmente inicializada: o primeiro
# `init` pode reconfigurar o placeholder, mas um `init` de espectador numa corrida
# já inicializada apenas reenvia o snapshot.
initialized_race_ids: set[str] = set()


def stop_engine(race_id: str, *, abort: bool = False) -> None:
    """Encerra e remove o motor e a task assíncrona de uma corrida.

    Args:
        race_id: Corrida a encerrar.
        abort: True quando a corrida acaba sem ninguém assistindo (último cliente
            saiu). Se ela estava sendo gravada e não terminou, vira `aborted`.
            Num `restart` é False: o motor novo vai limpar e regravar a corrida.
    """
    engine = active_engines.pop(race_id, None)
    if engine is not None:
        engine.stop()

    task = active_tasks.pop(race_id, None)
    if task is not None and not task.done():
        task.cancel()

    engine_generations.pop(race_id, None)
    initialized_race_ids.discard(race_id)

    gravador = active_recorders.pop(race_id, None)
    if gravador is not None:
        terminou = engine is not None and engine.state.is_finished
        if not abort:
            # Restart: o motor novo vai limpar e regravar; nada deste pode entrar depois.
            gravador.desativar()
        elif gravador.ativo:
            # Se a corrida terminou, o `on_finished` normalmente já gravou `finished` e
            # desativou o gravador; isto cobre o caso de a task ter sido cancelada antes.
            status = "finished" if terminou else "aborted"
            tarefa = asyncio.create_task(gravador.mudar_status(status))
            _pending_aborts[race_id] = tarefa

            def _esquecer(feita: asyncio.Task[None], r: str = race_id) -> None:
                # Só remove se ninguém registrou outra gravação para a mesma corrida.
                if _pending_aborts.get(r) is feita:
                    _pending_aborts.pop(r, None)

            tarefa.add_done_callback(_esquecer)


def _recording_hooks(race_id: str, gravador: GravadorDeCorrida) -> dict[str, Any]:
    """Ganchos `on_lap_closed`/`on_finished` do motor que gravam no banco.

    Falha de banco não derruba a corrida ao vivo: o erro é registrado, o gravador é
    desativado (para não deixar buracos no meio do histórico) e a transmissão segue.
    """

    async def on_lap_closed(voltas: list[LapResult], eventos: list[dict[str, Any]]) -> None:
        if not gravador.ativo:
            return
        try:
            await gravador.registrar_volta(voltas, eventos_do_motor(eventos))
        except Exception:
            logger.exception("Falha ao gravar volta da corrida %s; gravação desligada", race_id)
            gravador.desativar()

    async def on_finished() -> None:
        try:
            await gravador.mudar_status("finished")
        except Exception:
            logger.exception("Falha ao marcar a corrida %s como finished", race_id)

    return {"on_lap_closed": on_lap_closed, "on_finished": on_finished}


def _load_track_map(circuit_id: str) -> TrackMap | None:
    """Carrega o TrackMap do circuito, degradando para None se indisponível."""
    try:
        return TrackMap.load(circuit_id)
    except Exception as e:
        logger.warning(f"Não foi possível carregar TrackMap para '{circuit_id}': {e}")
        return None


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
    circuit_id: str = "interlagos",
    gravador: GravadorDeCorrida | None = None,
) -> RaceEngine:
    """Recupera a instância ativa do RaceEngine ou inicializa uma nova para a corrida.

    Com `gravador`, o motor novo grava cada volta fechada no banco. O gravador já
    deve estar preparado (`GravadorDeCorrida.preparar`).
    """
    if force_new:
        # Descarta completamente o motor anterior antes de criar o próximo.
        stop_engine(race_id)

    if race_id not in active_engines:
        generation = next(_generation_counter)
        engine_generations[race_id] = generation

        track_map = _load_track_map(circuit_id)
        comprimento = track_map.length_m if track_map is not None else 4309.0
        initial_state = state or montar_grid_inicial(track_length=comprimento)

        async def _broadcast(
            envelope: dict[str, Any],
            *,
            _race_id: str = race_id,
            _generation: int = generation,
        ) -> None:
            # Um motor substituído não pode mais falar com os clientes.
            if engine_generations.get(_race_id) != _generation:
                return

            clients = connected_clients.get(_race_id, set()).copy()
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
            track_map=track_map,
            **(_recording_hooks(race_id, gravador) if gravador is not None else {}),
        )
        if gravador is not None:
            active_recorders[race_id] = gravador
        active_engines[race_id] = engine
        active_tasks[race_id] = asyncio.create_task(engine.run())

    return active_engines[race_id]


async def _start_persisted_engine(race_id: str, force_new: bool) -> RaceEngine | None:
    """Cria o motor de uma corrida gravada no banco. None se a corrida não estiver lá.

    Grid, voltas, seed, clima e circuito vêm do banco; o payload do cliente é
    ignorado para essas corridas, para o que é gravado bater com o que foi criado.
    """
    if not force_new and race_id in active_engines:
        return active_engines[race_id]

    corrida = await carregar_corrida_do_banco(race_id)
    if corrida is None:
        return None

    # Desliga o motor e o gravador antigos ANTES de limpar o histórico.
    stop_engine(race_id)
    pendente = _pending_aborts.pop(race_id, None)
    if pendente is not None:
        await asyncio.gather(pendente, return_exceptions=True)

    gravador = GravadorDeCorrida(db_sessao.engine(), corrida.race_id)
    try:
        await gravador.preparar()
    except Exception:
        logger.exception("Não foi possível preparar a gravação da corrida %s", race_id)
        gravador = None

    config = corrida.config
    mapa = _load_track_map(corrida.circuit_id)
    comprimento = mapa.length_m if mapa is not None else 4309.0
    engine = get_or_create_engine(
        race_id=race_id,
        state=estado_inicial(corrida, comprimento),
        seed=corrida.seed,
        weather=str(config.get("weather", "DRY")),
        track_temp=float(config.get("track_temp", 32.0)),
        circuit_id=corrida.circuit_id,
        gravador=gravador,
    )
    # A corrida veio configurada do banco: já pode ser tratada como inicializada.
    initialized_race_ids.add(race_id)
    return engine


async def _handle_connection(websocket: WebSocket, race_id: str) -> None:
    await websocket.accept()
    connected_clients.setdefault(race_id, set()).add(websocket)

    engine = await _start_persisted_engine(race_id, force_new=False) or get_or_create_engine(
        race_id
    )

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
                if (
                    action == "init"
                    and race_id in active_engines
                    and race_id in initialized_race_ids
                    and not active_engines[race_id].state.is_finished
                ):
                    # Não reinicia corrida em andamento para nova aba/espectador
                    engine = active_engines[race_id]
                    await websocket.send_text(json.dumps(engine.get_lap_update_envelope()))
                    continue

                persisted = None
                if action in ("restart", "start", "init"):
                    persisted = await _start_persisted_engine(race_id, force_new=True)
                if persisted is not None:
                    engine = persisted
                    await websocket.send_text(json.dumps(engine.get_lap_update_envelope()))
                elif action in ("restart", "start", "init"):
                    # O setup envia o grid e os compostos escolhidos; sem isso a
                    # corrida sempre largaria com o grid padrão e pneus MEDIUM.
                    grid = payload.get("grid")
                    if not isinstance(grid, list) or not grid:
                        grid = None
                    else:
                        grid = [str(code) for code in grid][:20]

                    pneus = (
                        payload.get("initial_strategy")
                        or payload.get("initialStrategy")
                        or payload.get("initial_tyres")
                        or payload.get("initialTyres")
                    )
                    if not isinstance(pneus, dict) or not pneus:
                        pneus = None

                    circuit_id = (
                        payload.get("circuit_id") or payload.get("circuitId") or "interlagos"
                    )
                    track_map_setup = _load_track_map(circuit_id)
                    new_state = montar_grid_inicial(
                        grid=grid,
                        initial_tyres=pneus,
                        track_length=(
                            track_map_setup.length_m if track_map_setup is not None else 4309.0
                        ),
                    )
                    total_laps = payload.get("total_laps") or payload.get("totalLaps")
                    if total_laps is not None:
                        try:
                            new_state.total_laps = max(1, int(total_laps))
                        except (ValueError, TypeError):
                            pass

                    raw_seed = payload.get("seed", 42)
                    try:
                        seed_val = int(raw_seed)
                    except (ValueError, TypeError):
                        seed_val = 42

                    raw_track_temp = payload.get("track_temp") or payload.get("trackTemp")
                    try:
                        track_temp_val = (
                            float(raw_track_temp) if raw_track_temp is not None else 32.0
                        )
                    except (ValueError, TypeError):
                        track_temp_val = 32.0

                    engine = get_or_create_engine(
                        race_id=race_id,
                        state=new_state,
                        seed=seed_val,
                        weather=str(payload.get("weather", "DRY")),
                        track_temp=track_temp_val,
                        force_new=True,
                        circuit_id=circuit_id,
                    )
                    initialized_race_ids.add(race_id)
                    await websocket.send_text(json.dumps(engine.get_lap_update_envelope()))
                else:
                    engine.handle_command(payload)
            except (json.JSONDecodeError, ValueError, TypeError, KeyError) as err:
                logger.warning(f"Payload inválido ou erro no WebSocket ({race_id}): {err}")
    except WebSocketDisconnect:
        logger.info(f"Cliente WebSocket desconectado da corrida {race_id}")
    finally:
        clients = connected_clients.get(race_id)
        if clients is not None:
            clients.discard(websocket)
            if not clients:
                # Último cliente saiu: não faz sentido continuar simulando a
                # corrida antiga em segundo plano.
                connected_clients.pop(race_id, None)
                stop_engine(race_id, abort=True)


@router.websocket("/ws/races/{race_id}")
async def race_websocket_endpoint(websocket: WebSocket, race_id: str) -> None:
    """Endpoint oficial para conexão WebSocket por identificador de corrida."""
    await _handle_connection(websocket, race_id)


@router.websocket("/ws")
@router.websocket("/ws/")
async def generic_websocket_endpoint(websocket: WebSocket) -> None:
    """Endpoint genérico para clientes sem race_id explícito na URL."""
    await _handle_connection(websocket, "default")
