"""
Testes do Núcleo de Estado do Motor de Simulação (Fase 1 e Contrato D2)
========================================================================

Valida:
1. Estruturas de dados (RaceState, DriverState, LapResult) representando
   corretamente um grid completo de 20 pilotos sem perda de dados.
2. Contrato de tick(state, delta_time, track_length).
3. Serialização correta para o envelope formal lap_update do Contrato D2.
"""

from dataclasses import FrozenInstanceError

import pytest

from sim.state import (
    DriverState,
    LapResult,
    PitStatus,
    RaceState,
    TrackStatus,
    TyreCompound,
    format_lap_update,
    tick,
)

# Grid fictícia com 20 pilotos (2 por equipe, 10 equipes)
GRID_20_PILOTOS = [
    ("VER", "Max Verstappen", "Red Bull"),
    ("PER", "Sergio Pérez", "Red Bull"),
    ("HAM", "Lewis Hamilton", "Ferrari"),
    ("LEC", "Charles Leclerc", "Ferrari"),
    ("RUS", "George Russell", "Mercedes"),
    ("ANT", "Andrea Kimi Antonelli", "Mercedes"),
    ("NOR", "Lando Norris", "McLaren"),
    ("PIA", "Oscar Piastri", "McLaren"),
    ("ALO", "Fernando Alonso", "Aston Martin"),
    ("STR", "Lance Stroll", "Aston Martin"),
    ("GAS", "Pierre Gasly", "Alpine"),
    ("DOO", "Jack Doohan", "Alpine"),
    ("ALB", "Alexander Albon", "Williams"),
    ("SAI", "Carlos Sainz", "Williams"),
    ("TSU", "Yuki Tsunoda", "RB"),
    ("LAW", "Liam Lawson", "RB"),
    ("HUL", "Nico Hülkenberg", "Kick Sauber"),
    ("BOR", "Gabriel Bortoleto", "Kick Sauber"),
    ("OCO", "Esteban Ocon", "Haas"),
    ("BEA", "Oliver Bearman", "Haas"),
]


def montar_grid_inicial() -> RaceState:
    """Constrói um RaceState de largada com 20 pilotos em grid."""
    drivers = {}
    for grid_position, (driver_id, name, team) in enumerate(GRID_20_PILOTOS, start=1):
        drivers[driver_id] = DriverState(
            driver_id=driver_id,
            name=name,
            team=team,
            position=grid_position,
            lap_distance_covered=0.0,
            total_distance_covered=0.0,
            current_lap=0,
            last_lap_time=None,
            gap_to_leader=0.0 if grid_position == 1 else float(grid_position - 1) * 0.3,
            gap_to_ahead=None if grid_position == 1 else 0.3,
            tyre_compound=TyreCompound.MEDIUM,
            tyre_age=0,
            fuel_load=110.0,
            pit_status=PitStatus.NONE,
            pit_stops_made=0,
            is_retired=False,
            base_velocity=20.0,
            lap_time_sum=0.0,
            drs_active=False,
        )

    return RaceState(
        current_lap=0,
        total_laps=58,
        track_status=TrackStatus.GREEN,
        drivers=drivers,
        lap_history=[],
        elapsed_time=0.0,
        is_finished=False,
    )


@pytest.fixture
def race_state() -> RaceState:
    """Fixture do pytest: devolve um RaceState novo a cada teste."""
    return montar_grid_inicial()


# ---------------------------------------------------------------------------
# TESTES DE ESTRUTURA DA GRID
# ---------------------------------------------------------------------------


def test_grid_tem_exatamente_20_pilotos(race_state: RaceState):
    """A grid deve conter exatamente 20 pilotos, nem mais nem menos."""
    assert len(race_state.drivers) == 20


def test_ids_dos_pilotos_sao_unicos(race_state: RaceState):
    """Não pode haver dois pilotos com o mesmo driver_id na mesma corrida."""
    ids = [driver.driver_id for driver in race_state.drivers.values()]
    assert len(ids) == len(set(ids)), "Encontrado driver_id duplicado na grid"


def test_posicoes_de_largada_sao_unicas_e_sequenciais(race_state: RaceState):
    """As posições de largada devem cobrir 1..20 sem repetição e sem buracos."""
    posicoes = sorted(driver.position for driver in race_state.drivers.values())
    assert posicoes == list(range(1, 21))


def test_lider_nao_tem_gap_e_nao_tem_carro_a_frente(race_state: RaceState):
    """O piloto na posição 1 deve começar com gap 0 e sem gap_to_ahead."""
    lider = next(d for d in race_state.drivers.values() if d.position == 1)
    assert lider.gap_to_leader == 0.0
    assert lider.gap_to_ahead is None


def test_todos_os_pilotos_comecam_sem_pneu_usado_e_tanque_cheio(race_state: RaceState):
    """Estado de largada: pneu zerado, sem pit, sem paradas, sem abandono."""
    for driver in race_state.drivers.values():
        assert driver.tyre_age == 0
        assert driver.pit_status == PitStatus.NONE
        assert driver.pit_stops_made == 0
        assert driver.is_retired is False
        assert driver.fuel_load > 0


def test_historico_de_voltas_comeca_vazio(race_state: RaceState):
    """Antes da largada, nenhuma volta foi completada por ninguém."""
    assert race_state.lap_history == []


def test_corrida_comeca_na_volta_zero_e_nao_finalizada(race_state: RaceState):
    """current_lap deve começar em 0 e is_finished deve começar False."""
    assert race_state.current_lap == 0
    assert race_state.is_finished is False


# ---------------------------------------------------------------------------
# TESTE DE HISTÓRICO
# ---------------------------------------------------------------------------


def test_lap_history_comporta_resultado_de_volta_completa_para_20_pilotos(
    race_state: RaceState,
):
    """Simula o preenchimento de lap_history para a Volta 1."""
    volta_1 = []
    for driver in sorted(race_state.drivers.values(), key=lambda d: d.position):
        volta_1.append(
            LapResult(
                driver_id=driver.driver_id,
                lap_number=1,
                lap_time=90.0 + driver.position * 0.1,
                position=driver.position,
                gap_to_leader=driver.gap_to_leader,
                gap_to_ahead=driver.gap_to_ahead,
                tyre_compound=driver.tyre_compound,
                tyre_age=driver.tyre_age + 1,
                fuel_load=driver.fuel_load - 1.5,
                pit_stop=False,
            )
        )

    race_state.lap_history.extend(volta_1)

    assert len(race_state.lap_history) == 20
    posicoes_no_historico = [r.position for r in race_state.lap_history]
    assert posicoes_no_historico == list(range(1, 21))


def test_lap_result_e_imutavel(race_state: RaceState):
    """LapResult é frozen: tentar alterar um campo após criado deve falhar."""
    resultado = LapResult(
        driver_id="VER",
        lap_number=1,
        lap_time=90.5,
        position=1,
        gap_to_leader=0.0,
        gap_to_ahead=None,
        tyre_compound=TyreCompound.MEDIUM,
        tyre_age=1,
        fuel_load=108.5,
        pit_stop=False,
    )
    with pytest.raises(FrozenInstanceError):
        resultado.lap_time = 91.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TESTE DE CONTRATO: tick()
# ---------------------------------------------------------------------------


def test_tick_aumenta_numero_de_voltas(race_state: RaceState):
    """Testa o comportamento do tick() avançando tempo suficiente para cruzar a linha."""
    # 20 m/s * 200s = 4000m > 3337m
    tick(race_state, delta_time=200.0, track_length=3337.0)
    assert race_state.current_lap == 1
    assert len(race_state.lap_history) > 0


# ---------------------------------------------------------------------------
# TESTE DE SERIALIZAÇÃO: Contrato D2 (lap_update)
# ---------------------------------------------------------------------------


def test_format_lap_update_gera_envelope_valido(race_state: RaceState):
    """Garante que format_lap_update constrói o envelope estrito do Contrato D2."""
    envelope = format_lap_update(
        race_state,
        race_id="test-uuid",
        weather="DRY",
        track_temp=35.0,
    )
    assert envelope["type"] == "lap_update"
    assert envelope["race_id"] == "test-uuid"
    assert envelope["current_lap"] == 0
    assert envelope["total_laps"] == 58
    assert envelope["track_status"] == "GREEN"
    assert envelope["weather"] == "DRY"
    assert envelope["track_temp"] == 35.0

    drivers = envelope["drivers"]
    assert len(drivers) == 20
    # Ordenado por posição
    assert [d["position"] for d in drivers] == list(range(1, 21))

    # Verifica campos obrigatórios em cada piloto
    p1 = drivers[0]
    campos_esperados = [
        "driver_id",
        "name",
        "team",
        "position",
        "gap_to_leader",
        "gap_to_ahead",
        "last_lap_time",
        "tyre_compound",
        "tyre_age",
        "fuel_load_kg",
        "pit_status",
        "pit_stops_made",
        "is_retired",
        "drs_active",
        "distance_m",
    ]
    for campo in campos_esperados:
        assert campo in p1, f"Campo {campo} ausente no piloto do envelope"
