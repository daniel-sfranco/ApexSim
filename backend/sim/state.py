"""
Motor de Simulação de F1 — Núcleo de Estado (Marco M3)
======================================================

Este módulo define o CONTRATO de dados e comportamento do motor de
simulação:
- Estruturas de estado da corrida (`RaceState`, `DriverState`, `LapResult`).
- Função `tick()` com integração de física M3: degradação de pneu, consumo
  de combustível, esteira de ar sujo e ativação de DRS.
- Serialização para o envelope formal do Contrato D2 (`lap_update`).
- Pureza de domínio: zero dependências externas ou I/O web.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

from sim.physics import (
    dirty_air_time_delta,
    fuel_time_delta,
    is_drs_eligible,
    tyre_time_loss,
)

if TYPE_CHECKING:
    from sim.track import TrackMap


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
    """Registro imutável do resultado de UMA volta de UM piloto."""

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
    """Estado atual (mutável) de um piloto durante a corrida."""

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
    base_velocity: float  # Velocidade de referência em m/s
    lap_time_sum: float = 0.0  # Instante do último cruzamento de volta
    drs_active: bool = False  # True quando o piloto está com DRS aberto
    pit_time_remaining: float = 0.0  # Tempo restante parado no pit box (s)
    pit_stop_in_this_lap: bool = False  # Sinaliza pit stop na volta atual
    pit_time_in_this_lap: float | None = None  # Duração total da passagem no pit


# ---------------------------------------------------------------------------
# RACE STATE
# ---------------------------------------------------------------------------


@dataclass
class RaceState:
    """Estado completo da corrida em um instante da simulação."""

    current_lap: int
    total_laps: int
    track_status: TrackStatus
    drivers: dict[str, DriverState]
    elapsed_time: float
    lap_history: list[LapResult] = field(default_factory=list)
    is_finished: bool = False


# ---------------------------------------------------------------------------
# CONTRATO DO MOTOR: tick() com Física M3
# ---------------------------------------------------------------------------


def tick(
    state: RaceState,
    delta_time: float,
    track_length: float,
    rng: random.Random | None = None,
    track_map: TrackMap | None = None,
    track_temp: float = 35.0,
    use_physics: bool = False,
) -> RaceState:
    """Avança a simulação em um passo de tempo (tick) aplicando a física M3.

    Calcula a velocidade efetiva de cada carro modulada por:
    - Degradação de pneus (curvas calibradas de tyre_time_loss).
    - Queima de combustível (fuel_time_delta e redução de ~1.6 kg/volta).
    - Efeito aerodinâmico de ar sujo para carros colados (< 3.0s).
    - Ativação de DRS em zonas do TrackMap quando elegível (< 1.0s).
    - Limitação de velocidade e tempo de parada em pit stop.

    Args:
        state: Estado atual da corrida.
        delta_time: Intervalo de tempo simulado deste passo (em segundos).
        track_length: Extensão total do circuito em metros.
        rng: Gerador aleatório determinístico injetado.
        track_map: Mapa semântico de pista 1D (opcional).
        track_temp: Temperatura da pista em Celsius (default: 35°C).
        use_physics: Se True, aplica as penalidades e bônus físicos.
    """
    state.elapsed_time += delta_time
    rand_gauss = rng.gauss if rng is not None else random.gauss

    voltas_concluidas: list[tuple[DriverState, int, float]] = []
    lider_bandeirado = state.current_lap >= state.total_laps

    for driver in state.drivers.values():
        if (
            driver.is_retired
            or driver.current_lap >= state.total_laps
            or (lider_bandeirado and driver.current_lap < state.total_laps - 1)
        ):
            continue

        # 1) Gestão de Pit Stop em andamento
        tempo_movimento = delta_time
        if driver.pit_time_remaining > 0.0:
            tempo_parado = min(delta_time, driver.pit_time_remaining)
            driver.pit_time_remaining -= tempo_parado
            tempo_movimento = delta_time - tempo_parado
            if driver.pit_time_remaining <= 0.0:
                driver.pit_status = PitStatus.NONE

        # 2) Cálculo de velocidade efetiva com modelo de física M3
        if use_physics:
            # Tempo de referência base do circuito
            t_base = track_length / max(1.0, driver.base_velocity)

            # Composto
            comp_name = driver.tyre_compound.name.lower()
            if comp_name not in ("soft", "medium", "hard"):
                comp_name = "medium"

            # Perdas/ganhos físicos de tempo de volta (docs/fisica.md)
            t_tyre = tyre_time_loss(comp_name, driver.tyre_age, track_temp)  # type: ignore[arg-type]
            t_fuel = fuel_time_delta(driver.fuel_load)
            t_dirty = dirty_air_time_delta(driver.gap_to_ahead)

            # Avaliação de DRS
            drs_gain = 0.0
            if track_map is not None:
                in_drs_zone = track_map.is_drs_active(driver.lap_distance_covered)
                drs_ok = is_drs_eligible(
                    driver.gap_to_ahead,
                    current_lap=driver.current_lap,
                    track_status=state.track_status.name,
                )
                driver.drs_active = in_drs_zone and drs_ok
                if driver.drs_active:
                    drs_gain = 0.5  # Bônus de ritmo em zona de DRS (~10-12 km/h)
            else:
                driver.drs_active = False

            # Modulador de Safety Car / VSC
            sc_factor = 1.0
            if state.track_status == TrackStatus.SAFETY_CAR:
                sc_factor = 1.40  # Ritmo reduzido em 40% durante SC
            elif state.track_status == TrackStatus.YELLOW:
                sc_factor = 1.25  # VSC

            t_effective = max(10.0, (t_base + t_tyre + t_fuel + t_dirty - drs_gain) * sc_factor)
            v_eff = track_length / t_effective
        else:
            v_eff = driver.base_velocity

        # Limite de velocidade no pit lane (80 km/h = 22.2 m/s)
        if driver.pit_status == PitStatus.IN_PIT:
            v_eff = min(v_eff, 22.2)

        # 3) Deslocamento com ruído estocástico determinístico
        step_distance = max(0.0, (v_eff + rand_gauss(0, 0.4)) * tempo_movimento)

        # Consumo contínuo de combustível (~1.6 kg/volta)
        if track_length > 0:
            fuel_burned = 1.6 * (step_distance / track_length)
            driver.fuel_load = max(2.0, driver.fuel_load - fuel_burned)

        distancia_inicio_tick = driver.lap_distance_covered
        driver.lap_distance_covered += step_distance
        driver.total_distance_covered += step_distance

        # 4) Detecção de cruzamento da linha de chegada
        cruzamentos = 0
        while driver.lap_distance_covered >= track_length and track_length > 0:
            driver.lap_distance_covered -= track_length
            cruzamentos += 1

            distancia_ao_cruzamento = (
                track_length - distancia_inicio_tick + (cruzamentos - 1) * track_length
            )
            fracao = distancia_ao_cruzamento / step_distance if step_distance > 0 else 1.0
            instante_cruzamento = state.elapsed_time - delta_time + fracao * delta_time

            lap_time = instante_cruzamento - driver.lap_time_sum
            driver.lap_time_sum += lap_time
            driver.last_lap_time = lap_time
            driver.current_lap += 1
            driver.tyre_age += 1  # Incrementa idade do pneu na volta completa
            voltas_concluidas.append((driver, driver.current_lap, lap_time))

    # 5) Classificação: P1 é quem cobriu a maior distância total (ou menor tempo no encerramento)
    def chave_de_classificacao(driver: DriverState) -> tuple[int, float]:
        if driver.current_lap >= state.total_laps:
            return (0, driver.lap_time_sum)
        return (1, -driver.total_distance_covered)

    ordenados = sorted(state.drivers.values(), key=chave_de_classificacao)
    for posicao, driver in enumerate(ordenados, start=1):
        driver.position = posicao

    # 6) Cálculo de Gaps para líder e carro à frente
    cumulado_historico: dict[str, dict[int, float]] = {}
    for registro in state.lap_history:
        por_volta = cumulado_historico.setdefault(registro.driver_id, {})
        por_volta[registro.lap_number] = (
            por_volta.get(registro.lap_number - 1, 0.0) + registro.lap_time
        )

    def tempo_total_ate(outro: DriverState, n_volta: int) -> float:
        if n_volta >= outro.current_lap:
            return outro.lap_time_sum
        return cumulado_historico.get(outro.driver_id, {}).get(n_volta, 0.0)

    for posicao, driver in enumerate(ordenados, start=1):
        if posicao == 1:
            driver.gap_to_leader = 0.0
            driver.gap_to_ahead = None
        else:
            lider = ordenados[0]
            a_frente = ordenados[posicao - 2]
            driver.gap_to_leader = max(
                0.0,
                driver.lap_time_sum - tempo_total_ate(lider, driver.current_lap),
            )
            driver.gap_to_ahead = max(
                0.0,
                driver.lap_time_sum - tempo_total_ate(a_frente, driver.current_lap),
            )

    state.current_lap = ordenados[0].current_lap

    # 7) Registro das voltas concluídas no histórico
    for driver, lap_number, lap_time in sorted(
        voltas_concluidas, key=lambda item: item[0].position
    ):
        pit_stop = driver.pit_stop_in_this_lap
        pit_time = driver.pit_time_in_this_lap
        driver.pit_stop_in_this_lap = False
        driver.pit_time_in_this_lap = None

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
                pit_stop=pit_stop,
                pit_time=pit_time,
            )
        )

    return state


def todos_pilotos_finalizados(state: RaceState) -> bool:
    """True quando não resta ninguém na última volta após a bandeirada do líder."""
    if state.current_lap < state.total_laps:
        return False
    return not any(
        driver.current_lap == state.total_laps - 1
        for driver in state.drivers.values()
        if not driver.is_retired
    )


# ---------------------------------------------------------------------------
# SERIALIZAÇÃO PARA CONTRATO D2 (lap_update)
# ---------------------------------------------------------------------------


def format_lap_update(
    state: RaceState,
    race_id: str,
    weather: str = "DRY",
    track_temp: float = 32.0,
) -> dict:
    """Gera o envelope formal de telemetria `lap_update` (Contrato D2)."""
    drivers_ordenados = sorted(state.drivers.values(), key=lambda d: d.position)
    drivers_list = []
    for d in drivers_ordenados:
        compound_str = (
            d.tyre_compound.name
            if isinstance(d.tyre_compound, TyreCompound)
            else str(d.tyre_compound)
        )
        pit_str = d.pit_status.name if isinstance(d.pit_status, PitStatus) else str(d.pit_status)
        drivers_list.append(
            {
                "driver_id": d.driver_id,
                "name": d.name,
                "team": d.team,
                "position": int(d.position),
                "gap_to_leader": round(float(d.gap_to_leader), 3),
                "gap_to_ahead": (
                    round(float(d.gap_to_ahead), 3) if d.gap_to_ahead is not None else None
                ),
                "last_lap_time": (
                    round(float(d.last_lap_time), 3) if d.last_lap_time is not None else None
                ),
                "tyre_compound": compound_str,
                "tyre_age": int(d.tyre_age),
                "fuel_load_kg": round(float(d.fuel_load), 1),
                "pit_status": pit_str,
                "pit_stops_made": int(d.pit_stops_made),
                "is_retired": bool(d.is_retired),
                "drs_active": bool(getattr(d, "drs_active", False)),
                "distance_m": round(float(d.lap_distance_covered), 1),
            }
        )

    track_status_str = (
        state.track_status.name
        if isinstance(state.track_status, TrackStatus)
        else str(state.track_status)
    )

    return {
        "type": "lap_update",
        "race_id": str(race_id),
        "current_lap": int(state.current_lap),
        "total_laps": int(state.total_laps),
        "track_status": track_status_str,
        "weather": str(weather),
        "track_temp": float(track_temp),
        "drivers": drivers_list,
    }
