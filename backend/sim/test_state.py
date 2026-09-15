"""
Testes do Núcleo de Estado do Motor de Simulação (Fase 1)
==========================================================

Como tick() ainda não tem lógica implementada (é só contrato), estes
testes NÃO validam física de corrida. Eles validam duas coisas:

1. Que as estruturas de dados (RaceState, DriverState, LapResult)
   conseguem representar corretamente uma grid completa de 20 pilotos,
   sem perda ou corrupção de dados.
2. Que o contrato de tick() está sendo respeitado: ele deve aceitar
   (RaceState, delta_time) e, nesta fase, sempre levantar
   NotImplementedError — é assim que garantimos que ninguém vai
   confundir "ainda não implementado" com "implementado e retornando
   estado errado".

Rodar com:
    pytest test_simulation_engine.py -v
"""

from dataclasses import FrozenInstanceError

import pytest
from state import (
    DriverState,
    LapResult,
    PitStatus,
    RaceState,
    TrackStatus,
    TyreCompound,
    tick,
)

# ---------------------------------------------------------------------------
# FIXTURES / HELPERS
# ---------------------------------------------------------------------------
# Uma fixture do pytest é uma função que prepara dados/objetos reutilizáveis
# para os testes. Aqui, montamos uma grid de 20 pilotos uma única vez e
# reaproveitamos em vários testes, evitando repetir o mesmo boilerplate.

# Grid fictícia com 20 pilotos (2 por equipe, 10 equipes), para ter volume
# realista de um grid de F1 completo.
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
    """Constrói um RaceState de largada com 20 pilotos em grid.

    Todos começam na volta 0, sem gap acumulado, pneu MEDIUM novo,
    tanque cheio e fora do pit. Serve como "estado zero" para os testes
    e, futuramente, como ponto de partida real da simulação.
    """
    drivers = {}
    for grid_position, (driver_id, name, team) in enumerate(GRID_20_PILOTOS, start=1):
        drivers[driver_id] = DriverState(
            driver_id=driver_id,
            name=name,
            team=team,
            position=grid_position,
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
            total_race_time=0.0,
            base_lap_time=90.0 + grid_position * 0.1,  # Tempo base de volta, em segundos
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
    """Fixture do pytest: devolve um RaceState novo a cada teste.

    Recriar o estado em cada teste (em vez de compartilhar uma instância)
    evita que um teste "contamine" o estado usado por outro.
    """
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
# Como tick() não está implementado, este teste NÃO chama tick(). Ele
# valida que, se o histórico for populado manualmente (como o motor fará
# no futuro), a estrutura de LapResult comporta os 20 registros de uma
# volta completa, mantendo a ordenação por posição.


def test_lap_history_comporta_resultado_de_volta_completa_para_20_pilotos(
    race_state: RaceState,
):
    """Simula o preenchimento de lap_history para a Volta 1, sem tick()."""
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
    # Garante que o histórico manteve a ordem de posição e não misturou pilotos.
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
    """Testa o comportamento do tick() para uma volta completa."""
    # Simula o avanço de uma volta
    tick(race_state, delta_time=1.0)
    assert race_state.current_lap == 1
