"""Testes do modelo probabilístico de ultrapassagem (`sim/overtaking.py`).

Valida a forma da função de risco (monotonicidade e limites), os gates de
elegibilidade e a aplicação da ultrapassagem no estado da corrida.
"""

import random

import pytest

from sim.overtaking import (
    OVERTAKE_ATTACKER_COOLDOWN_S,
    OVERTAKE_BASE_ZONE_PROBABILITY,
    OVERTAKE_DRS_WEIGHT,
    OVERTAKE_MAX_GAP_S,
    OVERTAKE_MAX_ZONE_PROBABILITY,
    difficulty_weight,
    gap_weight,
    overtake_probability,
    pace_weight,
    sample_overtake,
    zone_difficulty,
)
from sim.run import montar_grid_inicial
from sim.state import RaceState, TrackStatus
from sim.track import TrackMap, Zone


class _AlwaysPass:
    """RNG falso que sempre sorteia 0.0 (ultrapassagem garantida)."""

    def random(self) -> float:
        return 0.0


@pytest.fixture
def mapa() -> TrackMap:
    """Circuito sintético com uma única zona de ultrapassagem (dificuldade média)."""
    return TrackMap(
        circuit_id="teste",
        length_m=4000,
        points=[],
        zones=[Zone("overtaking_spot", 0, 4000, {"difficulty": "media"})],
    )


def _duelo() -> RaceState:
    """Cria dois carros colados na volta 10 (estado novo a cada chamada)."""
    state = montar_grid_inicial(grid=["VER", "NOR"])
    state.total_laps = 50
    state.current_lap = 10

    for driver in state.drivers.values():
        driver.current_lap = 10

    ver = state.drivers["VER"]
    nor = state.drivers["NOR"]
    ver.total_distance_covered = 40000.0
    ver.lap_distance_covered = 2000.0
    ver.lap_time_sum = 1000.0
    nor.total_distance_covered = 39990.0
    nor.lap_distance_covered = 1990.0
    nor.lap_time_sum = 1000.5
    nor.gap_to_ahead = 0.5
    return state


@pytest.fixture
def duelo() -> RaceState:
    """Estado com NOR colado em VER, ambos na volta 10."""
    return _duelo()


def test_difficulty_weight():
    assert difficulty_weight("baixa") == pytest.approx(1.8)
    assert difficulty_weight("media") == pytest.approx(1.0)
    assert difficulty_weight("alta") == pytest.approx(0.5)
    assert difficulty_weight(None) == pytest.approx(1.0)
    assert difficulty_weight("desconhecida") == pytest.approx(1.0)


def test_zone_difficulty_prefers_explicit_prop():
    explicita = Zone("overtaking_spot", 0, 100, {"difficulty": "baixa"})
    assert zone_difficulty(explicita) == "baixa"


def test_zone_difficulty_inferred_from_type():
    frenagem = Zone("braking_zone", 0, 100, {"severity": "alta"})
    assert zone_difficulty(frenagem) == "alta"
    assert zone_difficulty(Zone("drs_activation", 0, 100)) == "media"
    assert zone_difficulty(Zone("corner", 0, 100)) is None


def test_pace_weight_monotonic_and_bounded():
    assert pace_weight(0.0) == pytest.approx(1.0)
    assert pace_weight(0.5) > pace_weight(0.1) > pace_weight(0.0)
    assert pace_weight(-0.5) < pace_weight(0.0)
    assert pace_weight(100.0) == pytest.approx(5.0)
    assert pace_weight(-100.0) == pytest.approx(0.05)


def test_gap_weight_decrescente():
    assert gap_weight(0.0) == pytest.approx(1.5)
    assert gap_weight(0.5) < gap_weight(0.2)
    assert gap_weight(5.0) == pytest.approx(0.5)


def test_zone_probability_uses_all_factors():
    neutro = overtake_probability(0.0, 0.5)
    assert neutro == pytest.approx(OVERTAKE_BASE_ZONE_PROBABILITY * 1.05)

    assert overtake_probability(0.5, 0.5) > neutro
    assert overtake_probability(0.0, 0.5, drs_active=True) > neutro
    assert overtake_probability(0.0, 0.5, difficulty="alta") < neutro


def test_probability_is_the_product_of_the_weights():
    """A tentativa é única por zona: P é o produto dos multiplicadores."""
    esperado = (
        OVERTAKE_BASE_ZONE_PROBABILITY
        * difficulty_weight("baixa")
        * pace_weight(0.3)
        * gap_weight(0.4)
        * OVERTAKE_DRS_WEIGHT
    )
    assert overtake_probability(0.3, 0.4, drs_active=True, difficulty="baixa") == pytest.approx(
        esperado
    )


def test_probability_is_bounded():
    for pace_delta in (-10.0, -0.5, 0.0, 0.5, 10.0):
        for gap in (0.0, 0.4, 0.8):
            p = overtake_probability(pace_delta, gap, difficulty="baixa")
            assert 0.0 <= p <= OVERTAKE_MAX_ZONE_PROBABILITY


def test_probability_rejects_negative_gap():
    with pytest.raises(ValueError):
        overtake_probability(0.0, -1.0)


def test_sample_overtake_gate_gap(duelo: RaceState, mapa: TrackMap):
    """Acima de OVERTAKE_MAX_GAP_S não há tentativa."""
    duelo.drivers["NOR"].gap_to_ahead = OVERTAKE_MAX_GAP_S + 0.5
    assert sample_overtake(duelo, mapa, _AlwaysPass()) == []


def test_sample_overtake_gate_track_status(duelo: RaceState, mapa: TrackMap):
    """Sob Safety Car/VSC não há ultrapassagem."""
    duelo.track_status = TrackStatus.SAFETY_CAR
    assert sample_overtake(duelo, mapa, _AlwaysPass()) == []


def test_sample_overtake_gate_zone(duelo: RaceState):
    """Fora de zona de ultrapassagem não há tentativa."""
    mapa_sem_zona = TrackMap(circuit_id="vazio", length_m=4000, points=[], zones=[])
    assert sample_overtake(duelo, mapa_sem_zona, _AlwaysPass()) == []


def test_sample_overtake_gate_cooldown(duelo: RaceState, mapa: TrackMap):
    """Cooldown ativo impede nova tentativa imediata."""
    duelo.drivers["NOR"].overtake_cooldown_s = 2.0
    assert sample_overtake(duelo, mapa, _AlwaysPass()) == []


def test_sample_overtake_swaps_position(duelo: RaceState, mapa: TrackMap):
    """Na confirmação, o atacante assume a posição e o relógio do defensor."""
    ver = duelo.drivers["VER"]
    nor = duelo.drivers["NOR"]

    resultados = sample_overtake(duelo, mapa, _AlwaysPass())

    assert len(resultados) == 1
    resultado = resultados[0]
    assert resultado.attacker_id == "NOR"
    assert resultado.defender_id == "VER"
    assert resultado.zone_id == "overtaking_spot:0-4000"

    assert nor.total_distance_covered > ver.total_distance_covered
    assert nor.lap_time_sum < ver.lap_time_sum
    assert nor.overtake_cooldown_s >= OVERTAKE_ATTACKER_COOLDOWN_S
    assert ver.overtake_cooldown_s > 0.0


def test_sample_overtake_is_deterministic(mapa: TrackMap):
    """Mesma seed reproduz o mesmo resultado (RNG injetado)."""
    res_a = sample_overtake(_duelo(), mapa, random.Random(7))
    res_b = sample_overtake(_duelo(), mapa, random.Random(7))

    assert [r.attacker_id for r in res_a] == [r.attacker_id for r in res_b]
