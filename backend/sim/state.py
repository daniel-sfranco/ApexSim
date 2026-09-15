"""
Motor de Simulação de F1 — Núcleo de Estado (Fase 1)
======================================================

Este módulo define apenas o CONTRATO de dados e comportamento do motor de
simulação: as estruturas que carregam o estado da corrida e a assinatura
da função que avança a simulação em um "tick" (passo de tempo/volta).

Nenhuma lógica de simulação é implementada aqui. O objetivo é fechar a
interface (quais dados existem, quais tipos têm, o que tick() recebe e
devolve) antes de implementar as regras de física/estratégia.
"""

import random
from dataclasses import dataclass, field
from enum import Enum, auto


class TyreCompound(Enum):
    """Composto de pneu montado no carro no momento do registro.

    SOFT, MEDIUM, HARD: compostos de pneu seco (slick).
    INTERMEDIATE, WET: compostos de chuva.
    UNKNOWN: caso o composto não seja conhecido (ex.: erro de leitura).
    """

    SOFT = auto()
    MEDIUM = auto()
    HARD = auto()
    INTERMEDIATE = auto()
    WET = auto()
    UNKNOWN = auto()


class PitStatus(Enum):
    """Situação do piloto em relação ao pit lane no tick atual.

    NONE: piloto está em pista, não interagindo com o pit.
    ENTERING: piloto está entrando no pit lane neste tick.
    IN_PIT: piloto está parado no box (troca de pneu/reparo).
    EXITING: piloto está saindo do pit lane de volta à pista.
    """

    NONE = auto()
    ENTERING = auto()
    IN_PIT = auto()
    EXITING = auto()


class TrackStatus(Enum):
    """Status geral da pista, usado para regras globais (bandeiras).

    GREEN: corrida normal.
    YELLOW: bandeira amarela (safety car virtual, cautela).
    SAFETY_CAR: safety car físico em pista.
    RED: bandeira vermelha (corrida interrompida).
    """

    GREEN = auto()
    YELLOW = auto()
    SAFETY_CAR = auto()
    RED = auto()


# ---------------------------------------------------------------------------
# LAP RESULT
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LapResult:
    """Registro imutável do resultado de UMA volta de UM piloto.

    Este objeto é o "histórico" da simulação: a cada volta completada,
    um LapResult é gerado e arquivado (ex.: em RaceState.lap_history).
    É `frozen=True` porque um resultado de volta já concluída não deve
    ser alterado depois — isso protege a integridade do histórico.

    Attributes:
        driver_id: Identificador único do piloto (ex.: código FIA "HAM").
        lap_number: Número da volta à qual este resultado se refere.
        lap_time: Tempo total da volta, em segundos.
        position: Posição do piloto na classificação ao final da volta.
        gap_to_leader: Diferença de tempo, em segundos, para o líder da
            corrida ao final da volta (0.0 se for o próprio líder).
        gap_to_ahead: Diferença de tempo, em segundos, para o carro
            imediatamente à frente (None se for o líder).
        tyre_compound: Composto de pneu utilizado durante essa volta.
        tyre_age: Idade do pneu em número de voltas rodadas com ele.
        fuel_load: Carga de combustível estimada ao final da volta, em kg.
        pit_stop: True se o piloto realizou uma parada nos boxes
            durante esta volta.
        pit_time: Duração da passagem pelo pit lane nesta volta, em
            segundos (None se pit_stop for False).
    """

    driver_id: str
    lap_number: int
    lap_time: float
    position: int
    gap_to_leader: float
    gap_to_ahead: float | None
    tyre_compound: TyreCompound
    tyre_age: int
    fuel_load: float
    pit_stop: bool
    pit_time: float | None = None


# ---------------------------------------------------------------------------
# DRIVER STATE
# ---------------------------------------------------------------------------


@dataclass
class DriverState:
    """Estado atual (mutável) de um piloto durante a corrida.

    Diferente de LapResult, que é um retrato fixo de uma volta já
    concluída, DriverState representa a situação do piloto "agora",
    e é atualizado a cada tick() da simulação.

    Attributes:
        driver_id: Identificador único do piloto.
        name: Nome de exibição do piloto.
        team: Nome da equipe.
        position: Posição atual na corrida.
        current_lap: Número da volta em que o piloto está.
        last_lap_time: Tempo da última volta completada, em segundos
            (None antes de completar a primeira volta).
        gap_to_leader: Diferença de tempo atual para o líder, em segundos.
        gap_to_ahead: Diferença de tempo atual para o carro à frente,
            em segundos (None se for o líder).
        tyre_compound: Composto de pneu atualmente montado.
        tyre_age: Quantidade de voltas já rodadas com o pneu atual.
        fuel_load: Combustível restante estimado, em kg.
        pit_status: Estado atual do piloto em relação ao pit lane.
        pit_stops_made: Número total de paradas já realizadas na corrida.
        is_retired: True se o piloto abandonou a corrida.
        total_race_time: Tempo total acumulado de corrida, em segundos.
    """

    driver_id: str
    name: str
    team: str
    position: int
    current_lap: int
    last_lap_time: float | None
    gap_to_leader: float
    gap_to_ahead: float | None
    tyre_compound: TyreCompound
    tyre_age: int
    fuel_load: float
    pit_status: PitStatus
    pit_stops_made: int
    is_retired: bool
    total_race_time: float
    base_lap_time: float  # Tempo base de volta, em segundos (para simulação simplificada)


# ---------------------------------------------------------------------------
# RACE STATE
# ---------------------------------------------------------------------------


@dataclass
class RaceState:
    """Estado completo da corrida em um instante da simulação.

    É o objeto "raiz" que o motor de simulação consome e produz a cada
    tick(). Contém o estado de todos os pilotos, o histórico de voltas
    já registradas e metadados globais da corrida (volta atual, status
    da pista etc).

    Attributes:
        current_lap: Volta atual da corrida (referência global, pode
            divergir levemente de DriverState.current_lap enquanto
            pilotos estão distribuídos pela pista).
        total_laps: Número total de voltas programadas para a corrida.
        track_status: Status geral da pista (verde, amarela, SC, etc.).
        drivers: Mapa de driver_id -> DriverState, com o estado atual
            de cada piloto.
        lap_history: Lista de LapResult acumulada, em ordem cronológica,
            com todas as voltas já concluídas por todos os pilotos.
        elapsed_time: Tempo total decorrido de corrida, em segundos,
            desde a largada.
        is_finished: True quando a corrida foi encerrada (todas as
            voltas cumpridas, bandeirada, ou interrompida em definitivo).
    """

    current_lap: int
    total_laps: int
    track_status: TrackStatus
    drivers: dict[str, DriverState]
    lap_history: list[LapResult] = field(default_factory=list)
    elapsed_time: float = 0.0
    is_finished: bool = False
    rng = random.random()  # Gerador de números aleatórios para eventos estocásticos


# ---------------------------------------------------------------------------
# CONTRATO DO MOTOR: tick()
# ---------------------------------------------------------------------------


def tick(state: RaceState, delta_time: float) -> RaceState:
    """Avança a simulação em um passo de tempo (ou de volta).
 
    Este é o contrato central do motor: dado um RaceState e um intervalo
    de tempo a avançar, a função deve produzir o próximo RaceState,
    aplicando as regras de física, estratégia, degradação de pneus,
    consumo de combustível e eventuais eventos de pit stop.
 
    Args:
        state: Estado atual da corrida, imediatamente antes deste tick.
        delta_time: Quantidade de tempo, em segundos, que este tick deve
            avançar na simulação. Permite tanto um motor orientado a
            tempo fixo (ex.: 0.1s por tick) quanto orientado a eventos.
 
    Returns:
        RaceState: O novo estado da corrida após aplicar este tick,
        incluindo atualizações de posição, tempos, gaps, pneus,
        combustível e status de pit de cada piloto, além de qualquer
        LapResult novo que tenha sido gerado neste passo.
 
    """
    for driver in state.drivers.values():
        # Simulação simplificada: cada piloto completa uma volta em base_lap_time
        driver.current_lap += 1
        # Adiciona variação aleatória.
        driver.last_lap_time = driver.base_lap_time + random.gauss(0, 1.0)
        driver.total_race_time += driver.last_lap_time
    for driver in state.drivers.values():
        sorted_drivers = sorted(
            state.drivers.values(),
            key=lambda d: d.total_race_time,
        )
        driver.position = sorted_drivers.index(driver) + 1
    for driver in state.drivers.values():
        if driver.position == 1:
            driver.gap_to_leader = 0.0
            driver.gap_to_ahead = None
        else:
            leader_time = next(d.total_race_time for d in state.drivers.values() if d.position == 1)
            ahead_time = next(
                d.total_race_time
                for d in state.drivers.values()
                if d.position == driver.position - 1
            )
            driver.gap_to_leader = driver.total_race_time - leader_time
            driver.gap_to_ahead = driver.total_race_time - ahead_time
    state.current_lap += 1
 
    # Registra o resultado desta volta no histórico. Isso precisa vir
    # DEPOIS do cálculo de posição/gap acima, pois LapResult é um
    # "retrato" da volta já concluída — todos os campos (posição, gaps)
    # já devem estar com os valores finais deste tick.
    # Iteramos em ordem de posição (não em ordem de dict) só para o
    # histórico ficar legível quando inspecionado depois (P1 primeiro).
    pilotos_em_ordem = sorted(state.drivers.values(), key=lambda d: d.position)
    for driver in pilotos_em_ordem:
        state.lap_history.append(
            LapResult(
                driver_id=driver.driver_id,
                lap_number=driver.current_lap,
                lap_time=driver.last_lap_time,
                position=driver.position,
                gap_to_leader=driver.gap_to_leader,
                gap_to_ahead=driver.gap_to_ahead,
                tyre_compound=driver.tyre_compound,
                tyre_age=driver.tyre_age,
                fuel_load=driver.fuel_load,
                pit_stop=False,  # lógica de pit ainda não implementada
                pit_time=None,
            )
        )
 
    for driver in state.drivers.values():
        print(
            f"Driver {driver.driver_id}: Lap {driver.current_lap}, "
            f"Last Lap Time {driver.last_lap_time:.2f}s, Total Time {driver.total_race_time:.2f}s, "
            f"Position {driver.position}, Gap to Leader {driver.gap_to_leader:.2f}s, "
            f"Gap to Ahead {driver.gap_to_ahead if driver.gap_to_ahead is not None else 'N/A'}s"
        )

    return state
 
