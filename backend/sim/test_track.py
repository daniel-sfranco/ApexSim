"""Testes dos helpers de domínio do TrackMap (Contrato D4).

Cobrem os valores de pit lane (`pit_lane`) e a cascata de zonas de ultrapassagem
usada pelo modelo probabilístico (`sim/overtaking.py`).
"""

import pytest

from sim.track import (
    PIT_LANE_FALLBACK_SPEED_LIMIT_KMH,
    PIT_LANE_FALLBACK_TIME_LOSS_S,
    TrackMap,
    Zone,
)


@pytest.fixture(scope="module")
def interlagos() -> TrackMap:
    return TrackMap.load("interlagos")


def test_pit_lane_values_from_track_map(interlagos: TrackMap):
    """Interlagos anota 80 km/h e 21 s na zona `pit_lane`."""
    zone = interlagos.get_pit_lane_zone()
    assert zone is not None
    assert interlagos.pit_speed_limit_kmh() == pytest.approx(80.0)
    assert interlagos.pit_speed_limit_ms() == pytest.approx(80.0 / 3.6)
    assert interlagos.pit_time_loss_s() == pytest.approx(21.0)


def test_pit_lane_falls_back_when_zone_missing():
    """Circuito sem `pit_lane` usa os valores de fallback do módulo."""
    mapa = TrackMap(circuit_id="sem-pit", length_m=1000, points=[], zones=[])
    assert mapa.get_pit_lane_zone() is None
    assert mapa.pit_speed_limit_kmh() == PIT_LANE_FALLBACK_SPEED_LIMIT_KMH
    assert mapa.pit_time_loss_s() == PIT_LANE_FALLBACK_TIME_LOSS_S


def test_pit_lane_ignores_invalid_props():
    """Props ausentes/inválidos não devem quebrar o cálculo."""
    mapa = TrackMap(
        circuit_id="pit-invalido",
        length_m=1000,
        points=[],
        zones=[Zone("pit_lane", 900, 1000, {"speed_limit_kmh": "n/a"})],
    )
    assert mapa.pit_speed_limit_kmh() == PIT_LANE_FALLBACK_SPEED_LIMIT_KMH
    assert mapa.pit_time_loss_s() == PIT_LANE_FALLBACK_TIME_LOSS_S


def test_overtaking_zone_prefers_overtaking_spot():
    """Quando existe `overtaking_spot`, ela vence as demais zonas."""
    mapa = TrackMap(
        circuit_id="teste",
        length_m=1000,
        points=[],
        zones=[
            Zone("straight", 0, 1000),
            Zone("overtaking_spot", 100, 200, {"difficulty": "media"}),
        ],
    )
    zona = mapa.get_overtaking_zone_at(150.0)
    assert zona is not None
    assert zona.type == "overtaking_spot"
    assert zona.props["difficulty"] == "media"


def test_overtaking_zone_does_not_double_count_drs_when_spots_exist():
    """Circuitos com `overtaking_spot` anotado não somam `drs_activation` como zona extra."""
    mapa = TrackMap(
        circuit_id="com-spots",
        length_m=1000,
        points=[],
        zones=[
            Zone("overtaking_spot", 100, 200, {"difficulty": "baixa"}),
            Zone("drs_activation", 500, 800),
        ],
    )
    assert mapa.get_overtaking_zone_at(150.0) is not None
    assert mapa.get_overtaking_zone_at(600.0) is None


def test_overtaking_zone_falls_back_when_circuit_has_no_spots():
    """Circuitos sem `overtaking_spot` usam `drs_activation` como fallback."""
    mapa = TrackMap(
        circuit_id="sem-spots",
        length_m=1000,
        points=[],
        zones=[Zone("drs_activation", 400, 800)],
    )
    zona = mapa.get_overtaking_zone_at(600.0)
    assert zona is not None
    assert zona.type == "drs_activation"
    assert mapa.get_overtaking_zone_at(600.0, fallback=False) is None


def test_drs_activation_zone_at():
    mapa = TrackMap(
        circuit_id="teste",
        length_m=1000,
        points=[],
        zones=[Zone("drs_activation", 400, 600)],
    )
    assert mapa.get_drs_activation_zone_at(500.0) is not None
    assert mapa.get_drs_activation_zone_at(100.0) is None
