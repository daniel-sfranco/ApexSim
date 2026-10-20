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


def test_engine_async_run_and_broadcast():
    """Testa o loop assíncrono emitindo envelopes via broadcast_fn até a bandeirada."""

    async def _run_test() -> None:
        emitted_laps: list[int] = []

        async def mock_broadcast(envelope: dict[str, Any]) -> None:
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
        # Volta 0 (grid), volta 1, volta 2, volta 3 (final)
        assert emitted_laps == [0, 1, 2, 3]

    asyncio.run(_run_test())


def test_realtime_loop_helper():
    """Valida o utilitário run_realtime_loop."""

    async def _run_test() -> None:
        emitted = []

        def sync_broadcast(env: dict[str, Any]) -> None:
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
        assert len(emitted) == 3  # 0, 1, 2

    asyncio.run(_run_test())
