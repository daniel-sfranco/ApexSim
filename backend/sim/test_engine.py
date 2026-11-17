"""
Testes do Orquestrador de Corrida (RaceEngine e realtime_loop)
==============================================================

Valida:
1. Conformidade do envelope `lap_update` com o Contrato D2.
2. Controles de fluxo: play, pause, resume, set_speed e stop.
3. Recepção e execução de comandos JSON do cliente.
4. Determinismo via injeção de seed no gerador de números aleatórios.
5. Loop assíncrono e disparo correto de callbacks via broadcast_fn.
"""

import asyncio
from typing import Any

import pytest

from sim.engine import RaceEngine
from sim.realtime_loop import run_realtime_loop
from sim.run import montar_grid_inicial
from sim.state import PitStatus, TyreCompound, tick
from sim.track import TrackMap


@pytest.fixture
def base_engine() -> RaceEngine:
    state = montar_grid_inicial()
    state.total_laps = 5
    return RaceEngine(
        race_state=state,
        track_length=4309.0,
        race_id="test-race-id",
        seed=42,
        weather="DRY",
        track_temp=32.0,
        base_lap_delay=0.01,
    )


def test_engine_initialization_and_envelope(base_engine: RaceEngine):
    """Garante que a inicialização cria um envelope lap_update estrito."""
    assert base_engine.race_id == "test-race-id"
    assert base_engine.is_paused is False
    assert base_engine.speed_multiplier == 1.0
    assert base_engine.state.current_lap == 0

    envelope = base_engine.get_lap_update_envelope()
    assert envelope["type"] == "lap_update"
    assert envelope["race_id"] == "test-race-id"
    assert envelope["current_lap"] == 0
    assert envelope["total_laps"] == 5
    assert envelope["track_status"] == "GREEN"
    assert envelope["weather"] == "DRY"
    assert envelope["track_temp"] == 32.0
    assert len(envelope["drivers"]) == 20
    assert envelope["drivers"][0]["position"] == 1


def test_engine_play_pause(base_engine: RaceEngine):
    """Testa alternância de estados de pausa."""
    assert base_engine.is_paused is False

    base_engine.pause()
    assert base_engine.is_paused is True
    assert not base_engine._pause_event.is_set()

    base_engine.play()
    assert base_engine.is_paused is False
    assert base_engine._pause_event.is_set()

    base_engine.pause()
    base_engine.resume()
    assert base_engine.is_paused is False
    assert base_engine._pause_event.is_set()


def test_engine_set_speed(base_engine: RaceEngine):
    """Testa alteração do multiplicador de velocidade com clamping."""
    base_engine.set_speed(5.0)
    assert base_engine.speed_multiplier == 5.0

    # Clamping inferior
    base_engine.set_speed(0.05)
    assert base_engine.speed_multiplier == 0.25

    # Clamping superior
    base_engine.set_speed(50.0)
    assert base_engine.speed_multiplier == 20.0


def test_engine_handle_command(base_engine: RaceEngine):
    """Valida o parser de comandos recebidos do cliente WebSocket."""
    base_engine.handle_command({"action": "pause"})
    assert base_engine.is_paused is True

    base_engine.handle_command({"action": "resume"})
    assert base_engine.is_paused is False

    base_engine.handle_command({"action": "set_speed", "speed_multiplier": 3.5})
    assert base_engine.speed_multiplier == 3.5

    base_engine.handle_command({"action": "play"})
    assert base_engine.is_paused is False

    base_engine.handle_command({"action": "stop"})
    assert base_engine.is_stopped is True


def test_engine_step_lap(base_engine: RaceEngine):
    """Testa avanço síncrono de volta no motor."""
    assert base_engine.state.current_lap == 0

    base_engine.step_lap()
    assert base_engine.state.current_lap == 1
    assert len(base_engine.state.lap_history) > 0

    base_engine.step_lap()
    assert base_engine.state.current_lap == 2


def test_bandeirada_espera_apenas_quem_esta_na_ultima_volta():
    """Só os pilotos na última volta precisam cruzar; a penúltima não."""
    state = montar_grid_inicial()
    state.total_laps = 2
    # HUL (15 m/s) ainda estará na última volta quando o líder bandeirar
    # e precisa cruzar a linha; BEA (8 m/s) estará na penúltima volta e
    # não precisa concluir a corrida.
    state.drivers["HUL"].base_velocity = 15.0
    state.drivers["BEA"].base_velocity = 8.0

    engine = RaceEngine(
        race_state=state,
        track_length=2000.0,
        seed=42,
        base_lap_delay=0.01,
    )

    for _ in range(50):
        engine.step_lap()
        if state.drivers["HUL"].current_lap < state.total_laps:
            # Enquanto falta piloto na última volta, a corrida segue em andamento.
            assert engine.state.is_finished is False
        if engine.state.is_finished:
            break

    assert engine.state.is_finished is True

    # Quem estava na última volta completou a distância.
    assert state.drivers["HUL"].current_lap == state.total_laps

    # Quem estava na penúltima volta não precisou terminar.
    assert state.drivers["BEA"].current_lap < state.total_laps - 1
    assert state.drivers["BEA"].position == 20

    # Congelados após a bandeirada: ninguém avança mais.
    distancias = {k: d.total_distance_covered for k, d in state.drivers.items()}
    voltas = {k: d.current_lap for k, d in state.drivers.items()}
    tick(state, delta_time=5.0, track_length=2000.0, rng=engine.rng)
    for driver_id, driver in state.drivers.items():
        assert driver.total_distance_covered == distancias[driver_id]
        assert driver.current_lap == voltas[driver_id]


def test_engine_determinism_with_seed():
    """Duas instâncias com a mesma seed e grid produzem os mesmos tempos e gaps."""
    state1 = montar_grid_inicial()
    engine1 = RaceEngine(race_state=state1, seed=123, track_length=3000.0)

    state2 = montar_grid_inicial()
    engine2 = RaceEngine(race_state=state2, seed=123, track_length=3000.0)

    for _ in range(3):
        engine1.step_lap()
        engine2.step_lap()

    env1 = engine1.get_lap_update_envelope()
    env2 = engine2.get_lap_update_envelope()

    # Posições e gaps devem ser rigorosamente idênticos
    for d1, d2 in zip(env1["drivers"], env2["drivers"], strict=True):
        assert d1["driver_id"] == d2["driver_id"]
        assert d1["position"] == d2["position"]
        assert d1["gap_to_leader"] == d2["gap_to_leader"]
        assert d1["last_lap_time"] == d2["last_lap_time"]


def test_step_tick_advances_distance_and_burns_fuel(base_engine: RaceEngine):
    """Verifica se step_tick(0.5) avança distância linear e queima combustível."""
    ver = base_engine.state.drivers["VER"]
    initial_dist = ver.lap_distance_covered
    initial_fuel = ver.fuel_load

    base_engine.step_tick(delta_time=0.5)

    assert ver.lap_distance_covered > initial_dist
    assert ver.fuel_load < initial_fuel
    # Em 0.5s a ~20m/s de velocidade base, o carro avança cerca de 9 a 11 metros
    assert 8.0 < (ver.lap_distance_covered - initial_dist) < 15.0


def test_step_tick_with_track_map():
    """Valida step_tick com mapa semântico de Interlagos carregado."""
    track_map = TrackMap.load("interlagos")
    state = montar_grid_inicial()
    engine = RaceEngine(
        race_state=state,
        track_map=track_map,
        seed=42,
    )
    assert engine.track_length == track_map.length_m
    engine.step_tick(delta_time=0.5)
    env = engine.get_lap_update_envelope()
    assert env["drivers"][0]["distance_m"] > 0


def test_step_tick_triggers_pit_stop_heuristic():
    """Simula piloto com pneus degradados na janela de pit e confirma acionamento de parada."""
    state = montar_grid_inicial()
    engine = RaceEngine(race_state=state, track_length=4000.0, seed=42)

    ver = state.drivers["VER"]
    ver.current_lap = 2
    ver.tyre_compound = TyreCompound.SOFT
    ver.tyre_age = 22  # Pneu soft muito gasto
    ver.lap_distance_covered = 3600.0  # 90% da pista (janela de entrada de pit)

    engine.step_tick(delta_time=0.5)

    assert ver.pit_status == PitStatus.IN_PIT
    assert ver.pit_time_remaining > 0
    assert len(engine.pending_events) == 1
    event = engine.pending_events[0]
    assert event["event_type"] == "PIT_STOP"
    assert event["involved_drivers"] == ["VER"]


def test_engine_async_run_and_broadcast():
    """Testa o loop assíncrono emitindo envelopes via broadcast_fn até a bandeirada."""

    async def _run_test() -> None:
        emitted_laps: list[int] = []

        async def mock_broadcast(envelope: dict[str, Any]) -> None:
            if envelope.get("type") == "lap_update":
                emitted_laps.append(envelope["current_lap"])

        state = montar_grid_inicial()
        state.total_laps = 3  # Corrida curta com 3 voltas

        engine = RaceEngine(
            race_state=state,
            track_length=2000.0,
            race_id="async-test",
            seed=42,
            base_lap_delay=0.01,  # Execução rápida para teste
            broadcast_fn=mock_broadcast,
        )

        await engine.run()

        assert engine.state.is_finished is True
        assert engine.state.current_lap == 3
        # Confirma que todas as voltas foram emitidas e houve telemetria tick-by-tick
        assert sorted(set(emitted_laps)) == [0, 1, 2, 3]
        assert len(emitted_laps) > 10

    asyncio.run(_run_test())


def test_realtime_loop_helper():
    """Valida o utilitário run_realtime_loop."""

    async def _run_test() -> None:
        emitted = []

        def sync_broadcast(env: dict[str, Any]) -> None:
            if env.get("type") == "lap_update":
                emitted.append(env["current_lap"])

        state = montar_grid_inicial()
        state.total_laps = 2

        engine = await run_realtime_loop(
            race_state=state,
            track_length=2000.0,
            base_lap_delay=0.01,
            broadcast_fn=sync_broadcast,
        )

        assert engine.state.is_finished is True
        assert sorted(set(emitted)) == [0, 1, 2]
        assert len(emitted) > 5

    asyncio.run(_run_test())
