"""
apexsim/physics.py

Funções puras de física de pneus, combustível, ar sujo e DRS para o ApexSim.
Fundamentação matemática completa em docs/fisica.md (Seções 1, 2, 3 e 4).

Convenção de sinal:
- tyre_grip retorna um fator de aderência normalizado (1.0 = grip máximo em pneu
  novo e temperatura ideal; decresce com idade e cliff).
- fuel_time_delta retorna segundos ADICIONAIS de tempo de volta devido à massa
  de combustível (0 = tanque vazio/mínimo).
- dirty_air_time_delta retorna segundos ADICIONAIS de tempo de volta devido à
  perda aerodinâmica na esteira turbulenta do carro à frente (>= 0).
- drs_lap_time_gain retorna segundos GANHOS (redução no tempo de volta, >= 0)
  pela abertura da asa móvel ao longo das zonas de ativação do circuito.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from app.models.track import TrackMap

Compound = Literal["soft", "medium", "hard"]


@dataclass(frozen=True)
class TyreParams:
    """Coeficientes por composto. Fonte: docs/fisica.md, Secao 1.3.

    Os coeficientes polinomiais (k1_quad, k2_lin) sao calibrados a partir do
    dataset Kaggle/FastF1 2023-2024 (entrega D5, curvas_degradacao.json).
    Os parametros de cliff (cliff_age, cliff_delta, cliff_beta) sao HIPOTESE
    DE MODELAGEM SEM DADO EMPIRICO: na faixa observada (ate 19 voltas no Soft,
    29 no Medium e 41 no Hard) nenhum cliff foi detectado (cliff: null), pois
    as equipes realizam o pit stop antes.
    """

    k1_quad: float  # s/volta^2 - calibrado no Kaggle 2023-2024 (D5)
    k2_lin: float  # s/volta   - degradacao linear calibrada no Kaggle 2023-2024 (D5)
    cliff_age: float  # voltas   - idade do cliff (hipotese sem dado, acima da faixa medida)
    cliff_delta: float  # s      - magnitude do salto no cliff (hipotese sem dado)
    cliff_beta: float  # 1/volta - inclinacao da transicao logistica (hipotese sem dado)


# k1_quad e k2_lin calibrados em data/curvas_degradacao/curvas_degradacao.json
# (39.966 voltas limpas, 44 GPs, idade_max_suportada: Soft=19, Medium=29, Hard=41).
# Nota: na faixa medida, o Hard apresenta degradacao superior ao Medium (ex.: idade 15:
# 0,80 s vs. 0,46 s); a hierarquia classica Soft > Medium > Hard e uma escolha de
# modelagem que se manifesta na vida util ate o cliff (25 < 35 < 47 voltas).
# Os parametros cliff_age (25.0, 35.0, 47.0), cliff_delta e cliff_beta sao hipoteses
# sem dado empirico posicionadas acima de idade_max_suportada para preservar a
# aderencia ao IC 95% medido em toda a regiao observada.
TYRE_TABLE: dict[Compound, TyreParams] = {
    "soft": TyreParams(
        k1_quad=0.002412, k2_lin=0.008639, cliff_age=25.0, cliff_delta=1.2, cliff_beta=0.9
    ),
    "medium": TyreParams(
        k1_quad=0.000847, k2_lin=0.015558, cliff_age=35.0, cliff_delta=0.8, cliff_beta=0.7
    ),
    "hard": TyreParams(
        k1_quad=0.0, k2_lin=0.051181, cliff_age=47.0, cliff_delta=0.5, cliff_beta=0.5
    ),
}

# Sensibilidade do grip a temperatura de pista fora da janela ideal.
# Fonte: estimado - nao ha coeficiente publico por composto; usa-se
# uma penalidade simetrica em torno de uma janela otima de 30-45 C
# (faixa qualitativa citada por Pirelli em comunicados tecnicos, sem
# valor numerico oficial -> tratado como ESTIMATIVA DECLARADA).
TRACK_TEMP_OPTIMAL = (30.0, 45.0)
TRACK_TEMP_PENALTY_PER_C = 0.004  # s/volta por grau fora da janela - estimado


def _cliff_term(age_laps: float, p: TyreParams) -> float:
    return p.cliff_delta / (1.0 + math.exp(-p.cliff_beta * (age_laps - p.cliff_age)))


def _temp_penalty(track_temp: float) -> float:
    lo, hi = TRACK_TEMP_OPTIMAL
    if track_temp < lo:
        return (lo - track_temp) * TRACK_TEMP_PENALTY_PER_C
    if track_temp > hi:
        return (track_temp - hi) * TRACK_TEMP_PENALTY_PER_C
    return 0.0


def tyre_time_loss(compound: Compound, age_laps: int, track_temp: float = 35.0) -> float:
    """Perda de tempo (s) em relacao ao pneu novo, na temperatura ideal.

    Equacao (docs/fisica.md Sec. 1.1):
        t_tire(a,c) = k1_quad*a^2 + k2_lin*a + cliff(a,c) + temp_penalty(T)

    Args:
        compound: "soft" | "medium" | "hard"
        age_laps: idade do pneu em voltas (>= 0)
        track_temp: temperatura de pista em graus Celsius

    Returns:
        Perda de tempo em segundos (sempre >= 0).
    """
    if age_laps < 0:
        raise ValueError("age_laps deve ser >= 0")
    if compound not in TYRE_TABLE:
        raise ValueError(f"composto desconhecido: {compound}")

    p = TYRE_TABLE[compound]
    quad_term = p.k1_quad * age_laps**2 + p.k2_lin * age_laps
    cliff = _cliff_term(age_laps, p)
    temp_pen = _temp_penalty(track_temp)
    return quad_term + cliff + temp_pen


def tyre_grip(compound: Compound, age_laps: int, track_temp: float = 35.0) -> float:
    """Fator de aderencia normalizado (1.0 = grip maximo de pneu novo).

    grip(a,c) = 1 / (1 + t_tire(a,c) / tau)

    onde tau e uma constante de escala (s) que converte perda de tempo em
    fracao de grip perdido. tau = 3.0 s e uma escolha de calibracao
    (ESTIMADO) tal que uma perda de ~3s de tempo de volta corresponda a
    ~50% de grip perdido, compativel com a ordem de grandeza do cliff
    termico descrito em docs/fisica.md Sec. 1.3.
    """
    tau = 3.0  # s - constante de escala, ESTIMADO
    loss = tyre_time_loss(compound, age_laps, track_temp)
    return 1.0 / (1.0 + loss / tau)


# ---------------------------------------------------------------------
# Combustivel - docs/fisica.md Secao 2
# ---------------------------------------------------------------------

# s/kg - fonte: McLaren Applied (citado em tese Politecnico di Torino,
# webthesis.biblio.polito.it/35913) e faixa da comunidade tecnica
# (r/F1Technical, F1Metrics): 0.03-0.08 s/kg. Valor pontual escolhido
# dentro da faixa reportada por McLaren -> nao e estimativa propria.
FUEL_SENSITIVITY_S_PER_KG = 0.03

FUEL_MAX_KG = 110.0  # kg - limite regulamentar FIA (fonte: regulamento tecnico)


def fuel_time_delta(fuel_kg: float) -> float:
    """Tempo adicional de volta (s) devido a massa de combustivel a bordo.

    Equacao (docs/fisica.md Sec. 2.1, forma reduzida):
        delta_t_fuel(m) = s_lap_mass * m

    Args:
        fuel_kg: massa de combustivel remanescente no carro, em kg (>=0)

    Returns:
        Segundos adicionais de tempo de volta em relacao ao carro sem
        combustivel (tanque a 0 kg).
    """
    if fuel_kg < 0:
        raise ValueError("fuel_kg deve ser >= 0")
    return FUEL_SENSITIVITY_S_PER_KG * fuel_kg


# ---------------------------------------------------------------------
# Ar Sujo (Aerodynamic Wake / Dirty Air) - docs/fisica.md Secao 3
# ---------------------------------------------------------------------

DIRTY_AIR_MAX_PENALTY_S = 0.42
DIRTY_AIR_MAX_DOWNFORCE_LOSS = 0.12
DIRTY_AIR_DECAY_S = 0.65
DIRTY_AIR_CUTOFF_S = 3.0


def dirty_air_time_delta(gap_ahead_s: float | None) -> float:
    """Penalidade de tempo de volta (s) causada pela esteira turbulenta do carro a frente."""
    if gap_ahead_s is None:
        return 0.0
    if gap_ahead_s < 0.0:
        raise ValueError("gap_ahead_s deve ser >= 0")
    if gap_ahead_s > DIRTY_AIR_CUTOFF_S:
        return 0.0
    return DIRTY_AIR_MAX_PENALTY_S * math.exp(-gap_ahead_s / DIRTY_AIR_DECAY_S)


def dirty_air_grip_factor(gap_ahead_s: float | None) -> float:
    """Multiplicador de aderencia aerodinamica sob efeito de ar sujo."""
    if gap_ahead_s is None:
        return 1.0
    if gap_ahead_s < 0.0:
        raise ValueError("gap_ahead_s deve ser >= 0")
    if gap_ahead_s > DIRTY_AIR_CUTOFF_S:
        return 1.0
    return 1.0 - DIRTY_AIR_MAX_DOWNFORCE_LOSS * math.exp(-gap_ahead_s / DIRTY_AIR_DECAY_S)


# ---------------------------------------------------------------------
# DRS (Drag Reduction System) - docs/fisica.md Secao 4
# ---------------------------------------------------------------------

DRS_GAP_THRESHOLD_S = 1.0
DRS_GAIN_PER_METER_S = 0.00045


def is_drs_eligible(
    gap_ahead_s: float | None,
    *,
    current_lap: int = 2,
    track_status: str = "GREEN",
    is_wet: bool = False,
    laps_since_restart: int = 2,
) -> bool:
    """Verifica se o piloto cumpre as regras esportivas da FIA para ativar o DRS."""
    if gap_ahead_s is None:
        return False
    if gap_ahead_s < 0.0:
        raise ValueError("gap_ahead_s deve ser >= 0")
    if track_status.upper() != "GREEN" or is_wet:
        return False
    if current_lap < 2 or laps_since_restart < 1:
        return False
    return gap_ahead_s < DRS_GAP_THRESHOLD_S


def drs_zone_time_gain(zone_length_m: float, *, eligible: bool = True) -> float:
    """Ganho de tempo (s) ao percorrer uma unica zona de ativacao de DRS de extensao L_DRS."""
    if zone_length_m < 0.0:
        raise ValueError("zone_length_m deve ser >= 0")
    if not eligible:
        return 0.0
    return DRS_GAIN_PER_METER_S * zone_length_m


def drs_lap_time_gain(
    track_map: TrackMap,
    gap_ahead_s: float | None,
    *,
    current_lap: int = 2,
    track_status: str = "GREEN",
    is_wet: bool = False,
    laps_since_restart: int = 2,
) -> float:
    """Ganho de tempo acumulado na volta (s) pelo uso de DRS nas zonas do TrackMap (Contrato D4)."""
    if not is_drs_eligible(
        gap_ahead_s,
        current_lap=current_lap,
        track_status=track_status,
        is_wet=is_wet,
        laps_since_restart=laps_since_restart,
    ):
        return 0.0

    has_detection = any(z.type == "drs_detection" for z in track_map.zones)
    if not has_detection:
        return 0.0

    total_drs_length_m = sum(z.length_m for z in track_map.zones if z.type == "drs_activation")
    return drs_zone_time_gain(total_drs_length_m, eligible=True)
