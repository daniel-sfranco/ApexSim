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
        base_velocity: Velocidade base de volta, em metros por segundo (para simulação do tempo, provisório)
        lap_time_sum: Soma dos tempos de volta para cálculo do tempo de volta
        lap_distance_covered: Distância percorrida na volta atual, em metros
            (zero ao cruzar a linha de chegada; volta ao zero a cada volta).
        total_distance_covered: Distância total acumulada na corrida, em
            metros (sempre cresce; usada para ordenar as posições).

    """

    driver_id: str
    name: str
    team: str
    position: int
    lap_distance_covered: float
    total_distance_covered: float
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
    base_velocity: float  # Velocidade base de volta, em metros por segundo (para simulação simplificada)
    lap_time_sum: float = 0.0  # Soma dos tempos de volta para cálculo do tempo de volta


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
    elapsed_time: float
    lap_history: list[LapResult] = field(default_factory=list)
    is_finished: bool = False


# ---------------------------------------------------------------------------
# CONTRATO DO MOTOR: tick()
# ---------------------------------------------------------------------------


def tick(state: RaceState, delta_time: float, track_length: float) -> RaceState:
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
        LapResult novo que tenha sido gerado neste passo (apenas para
        pilotos que concluíram uma volta durante este tick).

    """
    state.elapsed_time += delta_time

    # --- 1) Avança a distância de cada piloto e detecta conclusões de volta.
    # A distância é atualizada com base na velocidade base e em um ruído
    # aleatório (exatamente uma chamada de random.gauss por piloto por tick,
    # em ordem fixa de iteração — necessário para que a mesma seed produza
    # sempre a mesma corrida).
    voltas_concluidas: list[tuple[DriverState, int, float]] = []
    for driver in state.drivers.values():
        distancia_inicio_tick = driver.lap_distance_covered
        step_distance = (driver.base_velocity + random.gauss(0, 1)) * delta_time
        driver.lap_distance_covered += step_distance
        driver.total_distance_covered += step_distance

        cruzamentos = 0
        while driver.lap_distance_covered >= track_length:
            driver.lap_distance_covered -= track_length
            cruzamentos += 1
            # Distância (contada do início do tick) em que a linha foi
            # cruzada; dividida por step_distance dá a fração do tick em que
            # o cruzamento aconteceu. Assim registra-se o instante real do
            # cruzamento em vez do fim do tick — evita quantizar tempos de
            # volta e gaps em múltiplos de delta_time.
            distancia_ao_cruzamento = (
                track_length - distancia_inicio_tick
                + (cruzamentos - 1) * track_length
            )
            fracao = distancia_ao_cruzamento / step_distance
            instante_cruzamento = (
                state.elapsed_time - delta_time + fracao * delta_time
            )
            # Tempo da volta = instante deste cruzamento menos o instante do
            # cruzamento anterior. Na primeira volta lap_time_sum é 0, então
            # o resultado é o tempo decorrido desde a largada — correto
            # também nesse caso.
            lap_time = instante_cruzamento - driver.lap_time_sum
            driver.lap_time_sum += lap_time
            driver.last_lap_time = lap_time
            driver.current_lap += 1
            voltas_concluidas.append((driver, driver.current_lap, lap_time))

    # --- 2) Posições: P1 é quem cobriu a MAIOR distância total.
    ordenados = sorted(
        state.drivers.values(),
        key=lambda d: d.total_distance_covered,
        reverse=True,
    )
    for posicao, driver in enumerate(ordenados, start=1):
        driver.position = posicao

    # --- 3) Gaps por tempo de volta.
    # Cada piloto é comparado aos outros no MESMO número de voltas: o gap de
    # um piloto com N voltas é a diferença entre o tempo que ELE levou para
    # cumprir N voltas e o tempo que o outro piloto levou para cumprir as
    # mesmas N voltas (assim, quem está uma volta atrás não fica com gap
    # negativo). A cumulação por número de volta vem do lap_history; as
    # voltas concluídas AINDA NÃO registradas neste tick são cobertas pela
    # consulta direta a lap_time_sum (ver tempo_total_ate).
    cumulado_historico: dict[str, dict[int, float]] = {}
    for registro in state.lap_history:
        por_volta = cumulado_historico.setdefault(registro.driver_id, {})
        por_volta[registro.lap_number] = (
            por_volta.get(registro.lap_number - 1, 0.0) + registro.lap_time
        )

    def tempo_total_ate(outro: DriverState, n_volta: int) -> float:
        """Tempo cumulado que `outro` levou para concluir `n_volta` voltas."""
        if n_volta >= outro.current_lap:
            # Inclui (ou é exatamente) a volta mais recente de `outro`,
            # cujo lap_time_sum já está atualizado neste tick.
            return outro.lap_time_sum
        return cumulado_historico.get(outro.driver_id, {}).get(n_volta, 0.0)

    for posicao, driver in enumerate(ordenados, start=1):
        if posicao == 1:
            driver.gap_to_leader = 0.0
            driver.gap_to_ahead = None
        else:
            lider = ordenados[0]
            a_frente = ordenados[posicao - 2]
            # max(0.0, ...): a ordem por distância e a ordem por tempo de
            # volta podem divergir transientemente dentro da mesma volta;
            # o placar nunca deve exibir gap negativo.
            driver.gap_to_leader = max(
                0.0,
                driver.lap_time_sum - tempo_total_ate(lider, driver.current_lap),
            )
            driver.gap_to_ahead = max(
                0.0,
                driver.lap_time_sum - tempo_total_ate(a_frente, driver.current_lap),
            )

    state.current_lap = ordenados[0].current_lap  # A volta atual da corrida é a volta do líder

    # Registra no histórico APENAS as voltas concluídas neste tick. Cada
    # LapResult é um "retrato" da volta já concluída — todos os campos
    # (posição, gaps) já devem estar com os valores finais deste tick, por
    # isso esta etapa vem DEPOIS dos cálculos acima. Iteramos em ordem de
    # posição (não em ordem de dict) para o histórico ficar legível.
    for driver, lap_number, lap_time in sorted(
        voltas_concluidas, key=lambda item: item[0].position
    ):
        state.lap_history.append(
            LapResult(
                driver_id=driver.driver_id,
                lap_number=lap_number,
                lap_time=lap_time,
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

    for driver in ordenados:
        ultimo_tempo = (
            f"{driver.last_lap_time:.2f}s"
            if driver.last_lap_time is not None
            else "N/A"
        )
        print(
            f"Driver {driver.driver_id}: Lap {driver.current_lap}, "
            f"Last Lap Time {ultimo_tempo}, "
            f"Lap time sum {driver.lap_time_sum:.2f}s, "
            f"Distance Covered {driver.total_distance_covered:.2f}m, "
            f"Position {driver.position}, Gap to Leader {driver.gap_to_leader:.2f}s, "
            f"Gap to Ahead {driver.gap_to_ahead if driver.gap_to_ahead is not None else 'N/A'}s"
        )

    return state
