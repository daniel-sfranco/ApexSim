"""
sim/overtaking.py

Modelo probabilístico de ultrapassagem do ApexSim (Marco M3).

Fundamentação: docs/apexsim-implementacoes-m0-m5.md (M3 do motor) e docs/fisica.md.
Cada entrada em uma zona de ultrapassagem (Contrato D4) é uma tentativa de
Bernoulli, com probabilidade

    P = p_0 * w_zona * w_ritmo * w_DRS * w_gap

onde:
- p_0 é a probabilidade base de UMA tentativa (uma travessia de zona) com tudo
  neutro;
- w_zona vem da dificuldade anotada no `overtaking_spot` (Contrato D4);
- w_ritmo = exp(k * delta) cresce com a vantagem de ritmo do atacante;
- w_DRS reflete o ganho de velocidade punta com a asa móvel aberta;
- w_gap cresce quando o atacante está colado no defensor.

O motor sorteia no máximo uma tentativa por entrada em zona de ultrapassagem: o
cooldown do piloto cobre o tempo de travessia (`t_zona = comprimento /
velocidade média`). Assim a chance não depende do `delta_time` do tick nem de a
zona ser curta ou longa.

Domínio puro: sem I/O, sem dependências externas, RNG injetado.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sim.physics import fuel_time_delta, normalize_compound_name, tyre_time_loss
from sim.state import DriverState, PitStatus, RaceState, TrackStatus
from sim.weather import normalize_weather_state, weather_time_delta

if TYPE_CHECKING:
    from sim.track import TrackMap

# ---------------------------------------------------------------------------
# Parâmetros de calibração (módulo-level para permitir ajuste no M4)
# ---------------------------------------------------------------------------

# Probabilidade base de sucesso em UMA tentativa de ultrapassagem (uma travessia
# de zona) com ritmo, gap, DRS e dificuldade neutros. O motor faz no máximo uma
# tentativa por entrada em zona, então o valor já é o da travessia completa.
OVERTAKE_BASE_ZONE_PROBABILITY = 0.01

# Teto da probabilidade acumulada em uma travessia de zona.
OVERTAKE_MAX_ZONE_PROBABILITY = 0.90

# Gap máximo (s) para considerar que o atacante está ao alcance de uma passada.
OVERTAKE_MAX_GAP_S = 0.8

# Volta mínima (largada não conta como oportunidade de ultrapassagem).
OVERTAKE_MIN_LAP = 2

# Sensibilidade ao diferencial de ritmo (s/volta) e limites do multiplicador.
OVERTAKE_PACE_EXPONENT = 1.2
OVERTAKE_PACE_MIN = 0.05
OVERTAKE_PACE_MAX = 5.0

# Multiplicador do DRS ativo (~10-12 km/h de velocidade punta).
OVERTAKE_DRS_WEIGHT = 1.4

# Peso do gap: linear, decrescente, com piso e teto.
OVERTAKE_GAP_INTERCEPT = 1.5
OVERTAKE_GAP_SLOPE = 0.9
OVERTAKE_GAP_MIN = 0.5
OVERTAKE_GAP_MAX = 1.5

# Peso por dificuldade anotada na zona (`difficulty` do Contrato D4).
OVERTAKE_DIFFICULTY_WEIGHTS: dict[str, float] = {
    "baixa": 1.8,
    "media": 1.0,
    "alta": 0.5,
}

# Cooldown (s) para o atacante não emendar ultrapassagens e para o defensor
# não repassar imediatamente (efeito ping-pong).
OVERTAKE_ATTACKER_COOLDOWN_S = 4.0
OVERTAKE_DEFENDER_COOLDOWN_S = 3.0


@dataclass(frozen=True)
class OvertakeResult:
    """Resultado de uma ultrapassagem bem-sucedida em um tick."""

    attacker_id: str
    defender_id: str
    zone_id: str
    difficulty: str | None
    gap_s: float
    pace_delta_s: float
    probability: float


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def difficulty_weight(difficulty: str | None) -> float:
    """Multiplicador da zona de ultrapassagem a partir de `props.difficulty`.

    Zonas sem a propriedade caem em `media` (peso 1.0), preservando o
    comportamento neutro para mapas antigos.
    """
    if not difficulty:
        return 1.0
    return OVERTAKE_DIFFICULTY_WEIGHTS.get(str(difficulty).strip().lower(), 1.0)


def zone_difficulty(zone: object) -> str | None:
    """Dificuldade efetiva da zona de ultrapassagem.

    Usa `props.difficulty` quando anotada (Contrato D4). Sem a propriedade,
    infere a partir do tipo: zonas de frenagem herdam a `severity`, ativações
    de DRS são `media` e demais tipos ficam neutros.
    """
    props = getattr(zone, "props", {}) or {}
    explicit = props.get("difficulty")
    if explicit:
        return str(explicit).strip().lower()

    zone_type = str(getattr(zone, "type", ""))
    if zone_type == "braking_zone":
        severity = props.get("severity")
        return str(severity).strip().lower() if severity else "media"
    if zone_type == "drs_activation":
        return "media"
    return None


def zone_traversal_time(zone_length_m: float, speed_ms: float) -> float:
    """Tempo (s) para atravessar a zona na velocidade média do atacante."""
    if zone_length_m > 0.0 and speed_ms > 0.0:
        return max(zone_length_m / speed_ms, 1e-3)
    return 1.0


def pace_weight(pace_delta_s: float) -> float:
    """Multiplicador do diferencial de ritmo (positivo = atacante mais rápido)."""
    # Limita o expoente antes de exp() para evitar overflow em entradas extremas.
    exponent = _clamp(OVERTAKE_PACE_EXPONENT * pace_delta_s, -3.0, 3.0)
    return _clamp(math.exp(exponent), OVERTAKE_PACE_MIN, OVERTAKE_PACE_MAX)


def gap_weight(gap_ahead_s: float) -> float:
    """Multiplicador da proximidade: colado no defensor aumenta a chance."""
    return _clamp(
        OVERTAKE_GAP_INTERCEPT - OVERTAKE_GAP_SLOPE * gap_ahead_s,
        OVERTAKE_GAP_MIN,
        OVERTAKE_GAP_MAX,
    )


def overtake_probability(
    pace_delta_s: float,
    gap_ahead_s: float,
    *,
    drs_active: bool = False,
    difficulty: str | None = None,
) -> float:
    """Probabilidade de sucesso em UMA tentativa de ultrapassagem.

    O motor faz no máximo uma tentativa por entrada em zona (o cooldown cobre a
    travessia completa), então este é o valor usado no sorteio de Bernoulli.

    Args:
        pace_delta_s: tempo de volta do defensor menos o do atacante (s/volta).
        gap_ahead_s: gap atual para o carro à frente (s).
        drs_active: se o atacante está com DRS aberto.
        difficulty: dificuldade da zona (`baixa`, `media`, `alta`) ou None.

    Returns:
        Probabilidade em [0, OVERTAKE_MAX_ZONE_PROBABILITY].
    """
    if gap_ahead_s < 0.0:
        raise ValueError("gap_ahead_s deve ser >= 0")

    probability = OVERTAKE_BASE_ZONE_PROBABILITY
    probability *= difficulty_weight(difficulty)
    probability *= pace_weight(pace_delta_s)
    probability *= gap_weight(gap_ahead_s)
    if drs_active:
        probability *= OVERTAKE_DRS_WEIGHT
    return min(probability, OVERTAKE_MAX_ZONE_PROBABILITY)


def compound_name(driver: DriverState) -> str:
    """Nome do composto no vocabulário das funções de física (slicks e chuva)."""
    return normalize_compound_name(driver.tyre_compound, default="medium")


def estimate_lap_time(
    driver: DriverState,
    track_length: float,
    track_temp: float,
    weather: str = "seco",
) -> float:
    """Proxy do tempo de volta do piloto no tick atual (s).

    Espelha a composição usada por `sim.state.tick()` (base + pneu + clima + combustível),
    sem ar sujo nem DRS: aqui interessa o ritmo intrínseco de cada carro.
    """
    base = track_length / max(1.0, driver.base_velocity)
    comp = compound_name(driver)
    weather_state = normalize_weather_state(weather, default="seco")
    return (
        base
        + tyre_time_loss(comp, driver.tyre_age, track_temp)
        + weather_time_delta(comp, weather_state)
        + fuel_time_delta(driver.fuel_load)
    )


def _zone_identifier(zone: object) -> str:
    """Identificador estável e legível para o envelope `event_update` (D2)."""
    start = int(getattr(zone, "start_m", 0.0))
    end = int(getattr(zone, "end_m", 0.0))
    zone_type = str(getattr(zone, "type", "zone"))
    return f"{zone_type}:{start}-{end}"


def _swap_track_position(attacker: DriverState, defender: DriverState) -> None:
    """Inverte a ordem do par trocando posição física e relógio acumulado.

    O motor é 1D/temporal: os gaps saem de `lap_time_sum`, então trocar apenas
    `total_distance_covered` deixaria a torre com a ordem certa e os gaps errados.
    As duas voltas seguintes absorvem o delta (no máximo `OVERTAKE_MAX_GAP_S`).
    """
    attacker.lap_distance_covered, defender.lap_distance_covered = (
        defender.lap_distance_covered,
        attacker.lap_distance_covered,
    )
    attacker.total_distance_covered, defender.total_distance_covered = (
        defender.total_distance_covered,
        attacker.total_distance_covered,
    )
    attacker.lap_time_sum, defender.lap_time_sum = (
        defender.lap_time_sum,
        attacker.lap_time_sum,
    )
    attacker.position, defender.position = (
        defender.position,
        attacker.position,
    )


def sample_overtake(
    state: RaceState,
    track_map: TrackMap,
    rng: random.Random,
    *,
    track_temp: float = 35.0,
    weather: str = "seco",
) -> list[OvertakeResult]:
    """Sorteia ultrapassagens para todos os pares consecutivos elegíveis no tick.

    Percorre a classificação atual e avalia, para cada carro, o rival
    imediatamente à frente. Cada piloto tenta no máximo uma vez por entrada em
    zona (o cooldown cobre a travessia). A ultrapassagem é aplicada no estado
    (troca de posição) e o resultado é devolvido para o motor emitir o
    `event_update`.
    """
    if state.track_status != TrackStatus.GREEN:
        return []

    ordenados = sorted(
        (d for d in state.drivers.values() if not d.is_retired),
        key=lambda d: d.position,
    )

    resultados: list[OvertakeResult] = []
    for idx in range(1, len(ordenados)):
        attacker = ordenados[idx]
        defender = ordenados[idx - 1]

        if attacker.overtake_cooldown_s > 0.0:
            continue
        if attacker.pit_status != PitStatus.NONE or defender.pit_status != PitStatus.NONE:
            continue
        if attacker.current_lap < OVERTAKE_MIN_LAP:
            continue
        if attacker.current_lap >= state.total_laps or defender.current_lap >= state.total_laps:
            continue
        if attacker.current_lap != defender.current_lap:
            continue

        gap = attacker.gap_to_ahead
        if gap is None or gap < 0.0 or gap > OVERTAKE_MAX_GAP_S:
            continue

        zone = track_map.get_overtaking_zone_at(attacker.lap_distance_covered)
        if zone is None:
            continue

        attacker_lap_time = estimate_lap_time(
            attacker, track_map.length_m, track_temp, weather=weather
        )
        pace_delta = (
            estimate_lap_time(defender, track_map.length_m, track_temp, weather=weather)
            - attacker_lap_time
        )
        speed_ms = track_map.length_m / attacker_lap_time if attacker_lap_time > 0.0 else 0.0
        difficulty = zone_difficulty(zone)
        t_zone = zone_traversal_time(zone.length_m, speed_ms)
        probability = overtake_probability(
            pace_delta,
            gap,
            drs_active=attacker.drs_active,
            difficulty=difficulty,
        )

        # Uma tentativa por travessia de zona: o cooldown cobre a passagem
        # completa, evitando dezenas de sorteios dentro da mesma reta.
        attacker.overtake_cooldown_s = max(OVERTAKE_ATTACKER_COOLDOWN_S, t_zone)

        if rng.random() >= probability:
            continue

        _swap_track_position(attacker, defender)
        ordenados[idx], ordenados[idx - 1] = ordenados[idx - 1], ordenados[idx]
        defender.overtake_cooldown_s = OVERTAKE_DEFENDER_COOLDOWN_S
        resultados.append(
            OvertakeResult(
                attacker_id=attacker.driver_id,
                defender_id=defender.driver_id,
                zone_id=_zone_identifier(zone),
                difficulty=difficulty,
                gap_s=round(gap, 3),
                pace_delta_s=round(pace_delta, 3),
                probability=round(probability, 4),
            )
        )

    return resultados
