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
from sim.events import RaceIncident
from sim.physics import tyre_time_loss
from sim.realtime_loop import run_realtime_loop
from sim.run import montar_grid_inicial
from sim.state import PitStatus, TrackStatus, TyreCompound
from sim.track import TrackMap
from strategy.heuristic import PitDecision


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
    """Só os pilotos na última volta precisam cruzar; os atrasados não."""
    state = montar_grid_inicial(grid=["VER", "OCO", "MAG"], track_length=2000.0)
    state.total_laps = 2

    engine = RaceEngine(
        race_state=state,
        track_length=2000.0,
        seed=42,
        base_lap_delay=0.01,
    )

    ver = state.drivers["VER"]
    oco = state.drivers["OCO"]
    mag = state.drivers["MAG"]

    # Cenário de bandeirada montado de forma determinística: o líder já concluiu
    # as duas voltas, OCO está na última volta (falta meia volta) e MAG está duas
    # voltas atrás, portanto não precisa completar a corrida.
    ver.current_lap = 2
    ver.total_distance_covered = 2 * 2000.0
    ver.lap_distance_covered = 0.0
    oco.current_lap = 1
    oco.total_distance_covered = 2000.0 + 1500.0
    oco.lap_distance_covered = 1500.0
    mag.current_lap = 0
    mag.total_distance_covered = 100.0
    mag.lap_distance_covered = 100.0

    # Com OCO ainda na última volta, a corrida não pode encerrar.
    engine.step_tick(5.0)
    assert oco.current_lap == 1
    assert engine.state.is_finished is False

    # OCO cruza a linha e conclui a última volta: aí sim a corrida termina.
    for _ in range(20):
        engine.step_tick(5.0)
        if engine.state.is_finished:
            break

    assert engine.state.is_finished is True
    assert oco.current_lap == state.total_laps

    # Quem estava duas voltas atrás não precisou terminar.
    assert mag.current_lap < state.total_laps - 1

    # Congelados após a bandeirada: ninguém avança mais.
    distancias = {k: d.total_distance_covered for k, d in state.drivers.items()}
    voltas = {k: d.current_lap for k, d in state.drivers.items()}
    engine.step_tick(5.0)
    for driver_id, driver in state.drivers.items():
        assert driver.total_distance_covered == distancias[driver_id]
        assert driver.current_lap == voltas[driver_id]


def test_engine_determinism_with_seed():
    """Duas instâncias com a mesma seed e grid produzem os mesmos tempos e gaps."""
    state1 = montar_grid_inicial(track_length=3000.0)
    engine1 = RaceEngine(race_state=state1, seed=123, track_length=3000.0)

    state2 = montar_grid_inicial(track_length=3000.0)
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
    """Verifica se step_tick(0.5) avança a distância total e queima combustível."""
    ver = base_engine.state.drivers["VER"]
    initial_total = ver.total_distance_covered
    initial_fuel = ver.fuel_load

    base_engine.step_tick(delta_time=0.5)

    # Em 0.5s a ~60 m/s de velocidade base, o carro avança cerca de 28-30 m.
    deslocamento = ver.total_distance_covered - initial_total
    assert 20.0 < deslocamento < 35.0
    assert ver.fuel_load < initial_fuel


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
    state = montar_grid_inicial(track_length=4000.0)
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

        state = montar_grid_inicial(track_length=2000.0)
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


def test_ganchos_de_fim_de_volta_entregam_o_historico_uma_vez_por_volta():
    """`on_lap_closed` recebe cada `LapResult` exatamente uma vez, em lotes por volta."""

    async def _run_test() -> None:
        lotes: list[tuple[list[Any], list[dict[str, Any]]]] = []
        terminou: list[bool] = []

        async def on_lap_closed(voltas: list[Any], eventos: list[dict[str, Any]]) -> None:
            lotes.append((voltas, eventos))

        async def on_finished() -> None:
            terminou.append(True)

        state = montar_grid_inicial()
        state.total_laps = 3
        engine = RaceEngine(
            race_state=state,
            track_map=TrackMap.load("interlagos"),
            seed=7,
            base_tick_delay=0.0,
            on_lap_closed=on_lap_closed,
            on_finished=on_finished,
        )

        await engine.run()

        entregues = [volta for voltas, _ in lotes for volta in voltas]
        assert entregues == engine.state.lap_history  # nada perdido, nada repetido
        # Um lote por volta do líder (mais o fechamento final), nunca um por tick.
        assert len(lotes) <= state.total_laps + 1
        assert terminou == [True]
        # Todo evento emitido também foi entregue (nenhum ficou para trás no fim).
        assert engine._events_since_lap_closed == []

    asyncio.run(_run_test())


def test_motor_parado_nao_chama_on_finished():
    async def _run_test() -> None:
        chamadas: list[str] = []

        async def on_finished() -> None:
            chamadas.append("finished")

        state = montar_grid_inicial()
        state.total_laps = 50
        engine = RaceEngine(race_state=state, base_tick_delay=0.0, on_finished=on_finished)
        engine.stop()
        await engine.run()

        assert chamadas == []

    asyncio.run(_run_test())


def test_realtime_loop_helper():
    """Valida o utilitário run_realtime_loop."""

    async def _run_test() -> None:
        emitted = []

        def sync_broadcast(env: dict[str, Any]) -> None:
            if env.get("type") == "lap_update":
                emitted.append(env["current_lap"])

        state = montar_grid_inicial(track_length=2000.0)
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


# ---------------------------------------------------------------------------
# Pit lane (Contrato D4), eventos estocásticos e Safety Car (M3)
# ---------------------------------------------------------------------------


def _incidente(
    driver_id: str = "VER",
    *,
    consequence: str = "TIME_LOSS",
    retirement: bool = False,
    time_loss_s: float = 4.0,
) -> RaceIncident:
    return RaceIncident(
        driver_id=driver_id,
        lap_number=5,
        distance_m=1200.0,
        sector=1,
        is_braking_zone=True,
        severity="alta",
        runoff="brita",
        corner_name="S do Senna",
        consequence=consequence,  # type: ignore[arg-type]
        time_loss_s=time_loss_s,
        caused_retirement=retirement,
    )


def test_pit_lane_values_come_from_track_map():
    """O motor lê limite e perda de tempo do pit lane do Contrato D4."""
    mapa = TrackMap.load("interlagos")
    engine = RaceEngine(
        race_state=montar_grid_inicial(),
        seed=42,
        base_lap_delay=0.01,
        track_map=mapa,
    )

    assert engine.pit_lane_loss_s == pytest.approx(21.0)
    assert engine.pit_speed_limit_ms == pytest.approx(80.0 / 3.6)


def test_pit_stop_applies_track_map_time_loss(monkeypatch):
    """A parada usa `time_loss_s` da pista, não o valor fixo antigo."""

    def fake_evaluate(**_kwargs: Any) -> PitDecision:
        return PitDecision(should_pit=True, target_compound="hard", reason="TESTE")

    mapa = TrackMap.load("interlagos")
    state = montar_grid_inicial()
    engine = RaceEngine(
        race_state=state,
        seed=42,
        base_lap_delay=0.01,
        track_map=mapa,
    )
    monkeypatch.setattr(engine.pit_heuristic, "evaluate_driver", fake_evaluate)

    ver = state.drivers["VER"]
    ver.current_lap = 5
    ver.lap_distance_covered = 4000.0

    engine.step_tick(delta_time=0.5)

    assert ver.pit_stops_made == 1
    assert ver.pit_time_in_this_lap == pytest.approx(21.0)
    # O tick consumiu 0.5 s do tempo parado no box.
    assert ver.pit_time_remaining == pytest.approx(20.5)
    assert engine.pending_events[0]["event_type"] == "PIT_STOP"


def test_apply_incident_adds_time_loss_and_event():
    engine = RaceEngine(race_state=montar_grid_inicial(), seed=42, base_lap_delay=0.01)
    ver = engine.state.drivers["VER"]
    antes = ver.lap_time_sum

    engine._apply_incident(_incidente(time_loss_s=4.0))

    # A perda de tempo é aplicada fisicamente na pista, sem alterar lap_time_sum antes da hora
    assert ver.incident_time_remaining == pytest.approx(4.0)
    assert ver.lap_time_sum == pytest.approx(antes)
    assert ver.is_retired is False
    evento = engine.pending_events[-1]
    assert evento["event_type"] == "ACCIDENT"
    assert evento["involved_drivers"] == ["VER"]
    assert evento["zone_id"] is not None


def test_incident_slows_down_next_lap_physically():
    """Incidente de 4s freia o carro fisicamente e aumenta o tempo da volta."""
    state = montar_grid_inicial(grid=["VER", "NOR"], track_length=2000.0)
    state.total_laps = 5
    engine = RaceEngine(race_state=state, track_length=2000.0, seed=42)

    # Avança volta 1
    engine.step_lap()
    ver = state.drivers["VER"]
    assert ver.current_lap == 1
    volta_1_tempo = ver.last_lap_time
    assert volta_1_tempo is not None

    # Aplica incidente de 4s
    engine._apply_incident(_incidente("VER", time_loss_s=4.0))
    assert ver.incident_time_remaining == 4.0

    # Avança até VER concluir a volta 2. O incidente imobiliza o carro por 4 s,
    # então NOR pode assumir a liderança: `step_lap` para na volta do líder, que
    # pode não ser a do VER.
    ticks = 0
    while ver.current_lap < 2 and ticks < 2000:
        engine.step_tick(engine.delta_time)
        ticks += 1
    assert ver.current_lap == 2
    volta_2_tempo = ver.last_lap_time
    assert volta_2_tempo is not None
    # A volta 2 fica física e matematicamente mais lenta que a volta 1
    assert volta_2_tempo > volta_1_tempo + 3.0


def test_apply_incident_retires_driver():
    engine = RaceEngine(race_state=montar_grid_inicial(), seed=42, base_lap_delay=0.01)
    ver = engine.state.drivers["VER"]

    engine._apply_incident(_incidente(retirement=True))

    assert ver.is_retired is True
    tipos = [e["event_type"] for e in engine.pending_events]
    assert "RETIREMENT" in tipos
    assert "ACCIDENT" in tipos


def test_safety_car_deployment_updates_status_and_compresses_field():
    state = montar_grid_inicial()
    state.total_laps = 50
    engine = RaceEngine(
        race_state=state,
        seed=42,
        track_length=4309.0,
        base_lap_delay=0.01,
    )

    ordenados = sorted(state.drivers.values(), key=lambda d: d.position)
    for idx, driver in enumerate(ordenados):
        driver.current_lap = 10
        driver.lap_distance_covered = 1000.0
        driver.total_distance_covered = 10 * 4309 + 1000.0 - idx * 30.0
        driver.lap_time_sum = 1000.0 + idx * 0.8

    engine.race_control.state = "SC"
    engine.race_control.laps_remaining = 3
    engine._sync_track_status("GREEN", [])

    assert state.track_status == TrackStatus.SAFETY_CAR
    assert engine.pending_events[-1]["event_type"] == "SAFETY_CAR_DEPLOYED"

    ativos = sorted(state.drivers.values(), key=lambda d: d.position)
    for idx in range(1, 5):
        assert ativos[idx].gap_to_ahead == pytest.approx(0.5)


def test_safety_car_compression_with_different_laps_no_negative_lap_time():
    """Garante que compressão com pilotos em voltas diferentes não gera tempos negativos nem ignora
    pilotos."""
    state = montar_grid_inicial(grid=["VER", "PER", "HAM"], track_length=2000.0)
    state.total_laps = 10
    engine = RaceEngine(race_state=state, track_length=2000.0, seed=42)

    ver = state.drivers["VER"]
    per = state.drivers["PER"]
    ham = state.drivers["HAM"]

    ver.current_lap = 2
    ver.lap_distance_covered = 15.0
    ver.total_distance_covered = 2 * 2000.0 + 15.0

    per.current_lap = 1
    per.lap_distance_covered = 1900.0
    per.total_distance_covered = 1 * 2000.0 + 1900.0

    ham.current_lap = 1
    ham.lap_distance_covered = 1800.0
    ham.total_distance_covered = 1 * 2000.0 + 1800.0

    engine._compress_field()

    assert per.gap_to_leader == pytest.approx(0.5)
    assert ham.gap_to_leader == pytest.approx(1.0)
    assert per.current_lap == 1
    assert ham.current_lap == 1
    assert per.lap_distance_covered > 1900.0


def test_step_tick_samples_incidents_on_lap_crossing(monkeypatch):
    """Um cruzamento de linha dispara a amostragem de incidentes do piloto."""
    mapa = TrackMap.load("interlagos")
    state = montar_grid_inicial(grid=["VER", "NOR"])
    engine = RaceEngine(
        race_state=state,
        seed=42,
        base_lap_delay=0.01,
        track_map=mapa,
    )

    chamados: list[tuple[str, int]] = []

    def fake_incident(driver_id, lap_number, track_map, rng, **kwargs):  # noqa: ANN001
        chamados.append((driver_id, lap_number))
        return None

    monkeypatch.setattr("sim.engine.sample_driver_lap_incident", fake_incident)

    for driver in state.drivers.values():
        driver.current_lap = 3
        driver.lap_distance_covered = 4300.0
    engine._previous_race_lap = 3

    engine.step_tick(delta_time=0.5)

    assert chamados
    assert all(lap == 4 for _, lap in chamados)


# ---------------------------------------------------------------------------
# Adaptadores da heurística de estratégia (implementação engine-only)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("weather", "esperado"),
    [
        ("DRY", "dry"),
        ("seco", "dry"),
        ("DAMP", "damp"),
        ("UMIDO", "damp"),
        ("WET", "wet"),
        ("molhado", "wet"),
        ("desconhecido", "dry"),
    ],
)
def test_heuristic_weather_normalization(weather: str, esperado: str):
    """O clima do Contrato D2 é traduzido para o vocabulário da heurística."""
    engine = RaceEngine(
        race_state=montar_grid_inicial(),
        weather=weather,
        base_lap_delay=0.01,
    )
    assert engine.heuristic_weather == esperado


def test_evaluate_pit_stops_feed_weather_and_rival_context(monkeypatch):
    """Os adaptadores entregam clima e contexto do rival sem tocar nos dataclasses."""
    state = montar_grid_inicial(grid=["VER", "NOR", "LEC"], track_length=4000.0)
    engine = RaceEngine(
        race_state=state,
        weather="DAMP",
        track_length=4000.0,
        base_lap_delay=0.01,
    )

    ver = state.drivers["VER"]
    nor = state.drivers["NOR"]
    lec = state.drivers["LEC"]

    for driver in (ver, nor, lec):
        driver.current_lap = 5
        driver.lap_distance_covered = 1000.0
    ver.lap_distance_covered = 0.9 * 4000.0
    nor.gap_to_ahead = 0.7

    capturado: dict[str, Any] = {}

    def spy(**kwargs: Any) -> PitDecision:
        capturado.update(kwargs)
        return PitDecision(should_pit=False, reason="STAY_OUT")

    monkeypatch.setattr(engine.pit_heuristic, "evaluate_driver", spy)
    engine._evaluate_pit_stops()

    driver_state = capturado["driver_state"]
    race_state = capturado["race_state"]
    assert race_state["weather"] == "damp"
    assert race_state["current_lap"] == state.current_lap
    assert race_state["safety_car"] is False
    assert race_state["red_flag"] is False
    assert driver_state["gap_to_car_behind"] == pytest.approx(0.7)
    assert driver_state["rival_behind_pitted"] is False

    # Rival parou na volta anterior: undercut ativo.
    engine._last_pit_lap["NOR"] = 4
    engine._evaluate_pit_stops()
    assert capturado["driver_state"]["rival_behind_pitted"] is True

    # Fora da janela de undercut.
    engine._last_pit_lap["NOR"] = 1
    engine._evaluate_pit_stops()
    assert capturado["driver_state"]["rival_behind_pitted"] is False

    # Rival no box agora também configura undercut.
    engine._last_pit_lap.clear()
    nor.pit_status = PitStatus.IN_PIT
    engine._evaluate_pit_stops()
    assert capturado["driver_state"]["rival_behind_pitted"] is True


def test_race_adapter_marks_safety_car_only_for_full_sc():
    """VSC (YELLOW no Contrato D2) não é anunciado como Safety Car à heurística."""
    state = montar_grid_inicial()
    engine = RaceEngine(race_state=state, base_lap_delay=0.01)

    state.track_status = TrackStatus.SAFETY_CAR
    assert engine._strategy_race_state()["safety_car"] is True

    state.track_status = TrackStatus.YELLOW
    assert engine._strategy_race_state()["safety_car"] is False


def test_clima_molhado_dispara_troca_para_pneu_de_chuva():
    """Com pista molhada, a prioridade WEATHER da heurística passa a valer."""
    state = montar_grid_inicial(grid=["VER", "NOR"], track_length=4000.0)
    engine = RaceEngine(
        race_state=state,
        weather="WET",
        track_length=4000.0,
        base_lap_delay=0.01,
    )

    ver = state.drivers["VER"]
    nor = state.drivers["NOR"]
    for driver in (ver, nor):
        driver.current_lap = 5
        driver.lap_distance_covered = 1000.0
    ver.lap_distance_covered = 0.9 * 4000.0

    engine.step_tick(delta_time=0.5)

    assert ver.pit_stops_made == 1
    assert ver.tyre_compound == TyreCompound.WET
    evento = engine.pending_events[0]
    assert evento["event_type"] == "PIT_STOP"
    assert "WEATHER" in evento["description"]
    assert engine._last_pit_lap["VER"] == 5


def test_strategy_degradation_curve_uses_native_rain_compounds():
    """Compostos de chuva usam suas curvas nativas em `sim.physics` (M4)."""
    engine = RaceEngine(race_state=montar_grid_inicial(), base_lap_delay=0.01)

    assert engine._strategy_degradation_curve("wet", 10) == pytest.approx(
        tyre_time_loss("wet", 10, engine.track_temp)
    )
    assert engine._strategy_degradation_curve("INTERMEDIATE", 10) == pytest.approx(
        tyre_time_loss("intermediate", 10, engine.track_temp)
    )
    assert engine._strategy_degradation_curve("soft", 10) == pytest.approx(
        tyre_time_loss("soft", 10, engine.track_temp)
    )
    # Composto desconhecido degrada de forma segura para medium
    assert engine._strategy_degradation_curve("unknown", 10) == pytest.approx(
        tyre_time_loss("medium", 10, engine.track_temp)
    )


def test_clima_molhado_com_pneu_de_chuva_nao_quebra_heuristica():
    """Pneu de chuva já montado não deve estourar a projeção de degradação."""
    state = montar_grid_inicial(grid=["VER", "NOR"], track_length=4000.0)
    engine = RaceEngine(
        race_state=state,
        weather="WET",
        track_length=4000.0,
        base_lap_delay=0.01,
    )

    ver = state.drivers["VER"]
    nor = state.drivers["NOR"]
    for driver in (ver, nor):
        driver.current_lap = 5
        driver.lap_distance_covered = 1000.0
    ver.lap_distance_covered = 0.9 * 4000.0
    ver.tyre_compound = TyreCompound.WET
    ver.tyre_age = 5

    engine._evaluate_pit_stops()

    assert ver.tyre_compound == TyreCompound.WET
    assert ver.pit_stops_made <= 1


# ---------------------------------------------------------------------------
# Integração do Módulo Climático Dinâmico (M4)
# ---------------------------------------------------------------------------


def test_clima_dinamico_avanca_por_volta_e_emite_evento():
    """Transição da cadeia de Markov atualiza `weather` (D2) e enfileira `WEATHER_CHANGED`."""
    matriz_forca_chuva = {
        "seco": {"seco": 0.0, "umido": 1.0, "molhado": 0.0},
        "umido": {"seco": 0.0, "umido": 0.0, "molhado": 1.0},
        "molhado": {"seco": 0.0, "umido": 0.0, "molhado": 1.0},
    }
    state = montar_grid_inicial(grid=["VER", "NOR"], track_length=2000.0)
    state.total_laps = 5
    engine = RaceEngine(
        race_state=state,
        track_length=2000.0,
        seed=42,
        weather="DRY",
        base_lap_delay=0.01,
        dynamic_weather=True,
        weather_transition_probs=matriz_forca_chuva,
    )

    assert engine.weather == "DRY"

    engine.step_lap()
    assert engine.weather == "DAMP"
    assert engine.get_lap_update_envelope()["weather"] == "DAMP"
    eventos_clima = [e for e in engine.pending_events if e["event_type"] == "WEATHER_CHANGED"]
    assert len(eventos_clima) == 1
    assert eventos_clima[0]["involved_drivers"] == []

    engine.pending_events.clear()
    engine.step_lap()
    assert engine.weather == "WET"
    assert engine.get_lap_update_envelope()["weather"] == "WET"
    eventos_clima_2 = [e for e in engine.pending_events if e["event_type"] == "WEATHER_CHANGED"]
    assert len(eventos_clima_2) == 1


def test_clima_estatico_quando_dynamic_weather_desativado():
    """Com `dynamic_weather=False`, o clima inicial não sofre transições de Markov."""
    matriz_forca_chuva = {
        "seco": {"seco": 0.0, "umido": 1.0, "molhado": 0.0},
        "umido": {"seco": 0.0, "umido": 0.0, "molhado": 1.0},
        "molhado": {"seco": 0.0, "umido": 0.0, "molhado": 1.0},
    }
    state = montar_grid_inicial(grid=["VER", "NOR"], track_length=2000.0)
    state.total_laps = 4
    engine = RaceEngine(
        race_state=state,
        track_length=2000.0,
        seed=42,
        weather="DRY",
        base_lap_delay=0.01,
        dynamic_weather=False,
        weather_transition_probs=matriz_forca_chuva,
    )

    engine.step_lap()
    engine.step_lap()

    assert engine.weather == "DRY"
    assert not any(e["event_type"] == "WEATHER_CHANGED" for e in engine.pending_events)


def test_clima_umido_dispara_troca_para_intermediario():
    """Em pista DAMP, slicks disparam parada por WEATHER para pneus INTERMEDIATE."""
    state = montar_grid_inicial(grid=["VER", "NOR"], track_length=4000.0)
    engine = RaceEngine(
        race_state=state,
        weather="DAMP",
        track_length=4000.0,
        base_lap_delay=0.01,
    )

    ver = state.drivers["VER"]
    nor = state.drivers["NOR"]
    for driver in (ver, nor):
        driver.current_lap = 5
        driver.lap_distance_covered = 1000.0
    ver.lap_distance_covered = 0.9 * 4000.0

    engine.step_tick(delta_time=0.5)

    assert ver.pit_stops_made == 1
    assert ver.tyre_compound == TyreCompound.INTERMEDIATE
    assert engine.pending_events[0]["event_type"] == "PIT_STOP"
    assert "WEATHER" in engine.pending_events[0]["description"]


def test_incidentes_usam_grip_combinado_de_pneu_e_clima(monkeypatch):
    """Slick em pista molhada recebe grip combinado bem menor que pneu WET no gerador NHPP."""
    mapa = TrackMap.load("interlagos")
    state = montar_grid_inicial(grid=["VER", "NOR"])
    engine = RaceEngine(
        race_state=state,
        weather="WET",
        seed=42,
        base_lap_delay=0.01,
        track_map=mapa,
    )

    state.drivers["VER"].tyre_compound = TyreCompound.SOFT
    state.drivers["NOR"].tyre_compound = TyreCompound.WET

    grips_recebidos: dict[str, float] = {}

    def spy_incident(driver_id, lap_number, track_map, rng, **kwargs):  # noqa: ANN001
        grips_recebidos[driver_id] = kwargs["grip_factor"]
        return None

    monkeypatch.setattr("sim.engine.sample_driver_lap_incident", spy_incident)

    for driver in state.drivers.values():
        # Volta 1 (antes da janela de pit da volta 2) para manter VER com slick ao cruzar a linha
        driver.current_lap = 1
        driver.lap_distance_covered = 4305.0
    engine._previous_race_lap = 1

    engine.step_tick(delta_time=1.0)

    assert "VER" in grips_recebidos and "NOR" in grips_recebidos
    assert grips_recebidos["VER"] < grips_recebidos["NOR"]
    assert grips_recebidos["VER"] <= 0.30
    assert grips_recebidos["NOR"] >= 0.80
