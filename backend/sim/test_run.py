"""
Testes de sim/run.py
=====================

Este módulo testa a camada de CLI/bootstrap da simulação:
1. montar_grid_inicial() — integridade da grid inicial.
2. Parsing e execução de voltas determinísticas com tick().
3. Reprodutibilidade da seed determinística.
"""

import random

import pytest

from sim.run import montar_grid_inicial
from sim.state import DriverState, PitStatus, RaceState, TrackStatus, TyreCompound, tick

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------


def piloto(driver_id: str, base_velocity: float = 20.0, position: int = 1) -> DriverState:
    """Cria um DriverState mínimo com velocidade base para testar tick()."""
    return DriverState(
        driver_id=driver_id,
        name=driver_id,
        team="Equipe",
        position=position,
        lap_distance_covered=0.0,
        total_distance_covered=0.0,
        current_lap=0,
        last_lap_time=None,
        gap_to_leader=0.0,
        gap_to_ahead=None,
        tyre_compound=TyreCompound.MEDIUM,
        tyre_age=0,
        fuel_load=110.0,
        pit_status=PitStatus.NONE,
        pit_stops_made=0,
        is_retired=False,
        base_velocity=base_velocity,
        lap_time_sum=0.0,
        drs_active=False,
    )


def estado_com(pilotos: list[DriverState], total_laps: int = 58) -> RaceState:
    """Monta um RaceState mínimo a partir de uma lista de pilotos."""
    return RaceState(
        current_lap=0,
        total_laps=total_laps,
        track_status=TrackStatus.GREEN,
        drivers={d.driver_id: d for d in pilotos},
        lap_history=[],
        elapsed_time=0.0,
        is_finished=False,
    )


# ---------------------------------------------------------------------------
# TESTES: cálculo de posição e gap
# ---------------------------------------------------------------------------


def test_lider_fica_em_primeiro_com_maior_velocidade(monkeypatch):
    """Sem ruído aleatório, quem tem maior velocidade base cobre maior distância e fica em P1."""
    monkeypatch.setattr(random, "gauss", lambda mu, sigma: 0.0)
    estado = estado_com(
        [
            piloto("A", base_velocity=20.0),
            piloto("B", base_velocity=25.0),  # mais rápido
            piloto("C", base_velocity=18.0),
        ]
    )

    tick(estado, delta_time=200.0, track_length=3000.0)

    assert estado.drivers["B"].position == 1
    assert estado.drivers["A"].position == 2
    assert estado.drivers["C"].position == 3


def test_lider_tem_gap_zero_e_gap_ahead_none(monkeypatch):
    """O piloto em P1 deve sempre ter gap_to_leader=0 e gap_to_ahead=None."""
    monkeypatch.setattr(random, "gauss", lambda mu, sigma: 0.0)
    estado = estado_com([piloto("A", 20.0), piloto("B", 25.0)])

    tick(estado, delta_time=200.0, track_length=3000.0)

    lider = estado.drivers["B"]
    assert lider.gap_to_leader == 0.0
    assert lider.gap_to_ahead is None


def test_current_lap_avanca_apos_cruzar_distancia_da_pista(monkeypatch):
    """Quando os pilotos cruzam track_length, current_lap é incrementado."""
    monkeypatch.setattr(random, "gauss", lambda mu, sigma: 0.0)
    # 20 m/s * 100s = 2000m >= 2000m -> 1 volta
    estado = estado_com([piloto("A", 20.0), piloto("B", 20.0)])

    tick(estado, delta_time=100.0, track_length=2000.0)
    assert estado.current_lap == 1
    assert all(d.current_lap == 1 for d in estado.drivers.values())

    tick(estado, delta_time=100.0, track_length=2000.0)
    assert estado.current_lap == 2
    assert all(d.current_lap == 2 for d in estado.drivers.values())


# ---------------------------------------------------------------------------
# TESTES: determinismo via seed
# ---------------------------------------------------------------------------


def _rodar_simulacao(seed: int) -> list[tuple[str, int, float]]:
    random.seed(seed)
    estado = montar_grid_inicial()
    for _ in range(10):
        tick(estado, delta_time=20.0, track_length=3337.0)
    return sorted(
        (d.driver_id, d.position, round(d.total_distance_covered, 3))
        for d in estado.drivers.values()
    )


def test_mesma_seed_produz_corrida_identica():
    """Rodar a simulação duas vezes com a mesma seed deve dar o mesmo resultado final."""
    resultado_1 = _rodar_simulacao(seed=42)
    resultado_2 = _rodar_simulacao(seed=42)

    assert resultado_1 == resultado_2


def test_seeds_diferentes_tendem_a_produzir_corridas_diferentes():
    """Seeds diferentes produzem distâncias acumuladas distintas."""
    resultado_1 = _rodar_simulacao(seed=1)
    resultado_2 = _rodar_simulacao(seed=2)

    assert resultado_1 != resultado_2


# ---------------------------------------------------------------------------
# TESTES: histórico de voltas
# ---------------------------------------------------------------------------


def test_tick_registra_lap_result_no_historico(monkeypatch):
    """Ao cruzar a linha, gera um LapResult por piloto e anexa em lap_history."""
    monkeypatch.setattr(random, "gauss", lambda mu, sigma: 0.0)
    estado = estado_com([piloto("A", 20.0), piloto("B", 20.0)])

    tick(estado, delta_time=100.0, track_length=2000.0)

    assert len(estado.lap_history) == 2


def test_lap_result_reflete_os_dados_corretos_do_piloto(monkeypatch):
    """Os campos do LapResult devem bater com o estado do piloto."""
    monkeypatch.setattr(random, "gauss", lambda mu, sigma: 0.0)
    estado = estado_com([piloto("A", 20.0), piloto("B", 25.0)])

    tick(estado, delta_time=100.0, track_length=2000.0)

    resultado_a = next(r for r in estado.lap_history if r.driver_id == "A")
    driver_a = estado.drivers["A"]

    assert resultado_a.lap_number == 1
    assert resultado_a.lap_time == pytest.approx(driver_a.last_lap_time)
    assert resultado_a.position == driver_a.position
    assert resultado_a.pit_stop is False


# ---------------------------------------------------------------------------
# TESTES: grid e compostos iniciais escolhidos no setup
# ---------------------------------------------------------------------------


def test_montar_grid_inicial_respeita_grid_e_compostos():
    """O grid enviado pelo setup define a ordem e os compostos de cada piloto."""
    grid = ["NOR", "VER", "COL", "MAG"]
    pneus = {"NOR": "SOFT", "VER": "HARD", "COL": "intermediate", "MAG": "X"}

    estado = montar_grid_inicial(grid=grid, initial_tyres=pneus)

    assert list(estado.drivers) == grid
    assert [d.position for d in estado.drivers.values()] == [1, 2, 3, 4]
    assert estado.drivers["NOR"].tyre_compound is TyreCompound.SOFT
    assert estado.drivers["VER"].tyre_compound is TyreCompound.HARD
    assert estado.drivers["COL"].tyre_compound is TyreCompound.INTERMEDIATE
    # Composto desconhecido cai no padrão.
    assert estado.drivers["MAG"].tyre_compound is TyreCompound.MEDIUM


def test_montar_grid_inicial_inclui_pilotos_fora_do_grid_padrao():
    """Códigos do setup ausentes do grid padrão usam o catálogo de pilotos."""
    estado = montar_grid_inicial(grid=["COL"])

    assert estado.drivers["COL"].name == "Franco Colapinto"
    assert estado.drivers["COL"].team == "Williams"


def test_montar_grid_inicial_sem_argumentos_mantem_grid_padrao():
    """Sem payload do setup, o comportamento antigo (20 pilotos) é preservado."""
    estado = montar_grid_inicial()

    assert len(estado.drivers) == 20
    assert all(d.tyre_compound is TyreCompound.MEDIUM for d in estado.drivers.values())
