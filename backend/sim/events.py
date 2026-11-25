"""
sim/events.py

Gerador estocástico de acidentes por zona (Processo de Poisson Não-Homogêneo)
e máquina de estados de Safety Car / VSC para o ApexSim (Marco M3).

Fundamentação matemática e estatística em docs/fisica.md (Seção 5):
1. Intensidade espacial de incidente ao longo do circuito (Seção 5.1):
       lambda(s) = lambda_base * w_braking(s) * w_grip(s) * w_weather(t) * w_aggression
   onde w_braking(s) = 1 + gamma_1 * 1[braking_zone](s) amplifica a taxa de risco
   nas zonas de frenagem anotadas no TrackMap (Contrato D4).
2. Severidade e consequência via modelo logístico (Seção 5.2):
       P(SC | incidente, runoff, severity) = sigma(alpha_0 + alpha_runoff + alpha_sev)
   mapeando o tipo de escapatória (`brita`, `muro` vs. `asfalto`) para a probabilidade
   de acionamento de Safety Car pleno (SC), Virtual Safety Car (VSC) ou apenas perda
   de tempo local (lock-up / escapada sem neutralização).
3. Calibração empírica (Seção 5.4, Auto Motor und Sport 2022 [25] e F1 Wiki [26]):
   ~1,0–1,1 SC e ~0,95 VSC por corrida em média, com duração típica de 2–4 voltas
   para SC pleno e 1–2 voltas para VSC.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from sim.track import TrackMap, Zone

WeatherCondition = Literal["seco", "umido", "molhado"]
IncidentConsequence = Literal["TIME_LOSS", "VSC", "SC"]
RaceControlState = Literal["GREEN", "VSC", "SC"]

# ---------------------------------------------------------------------------
# Parâmetros de Calibração — Seção 5 de docs/fisica.md
# ---------------------------------------------------------------------------

# Intensidade base de incidente por metro de pista em ar livre (fora de frenagem)
# para um único carro (1/m).
# Calibração (hipótese de modelagem calibrada sobre a estatística agregada de 2022,
# docs/fisica.md Seção 5.4 [25]): lambda_base = 2.4e-7 /m produz, na média dos 3
# circuitos do projeto (20 carros x 58 voltas), ~0.9–1.2 SC/corrida e ~0.8–1.0 VSC/corrida,
# com maior incidência de SC em Mônaco (escapatórias em muro) que em Interlagos e Monza.
BASE_INCIDENT_INTENSITY_PER_M = 2.4e-7

# Amplificação de risco por severidade de frenagem w_braking(s) = 1 + gamma_1 (Eq. 259).
# Hipótese calibrada para concentrar ~65-75% dos incidentes nas zonas de desaceleração.
BRAKING_SEVERITY_WEIGHTS: dict[str, float] = {
    "baixa": 6.0,
    "media": 11.0,
    "alta": 18.0,
}

# Multiplicador de risco climático w_weather(t) (docs/fisica.md Seção 5.1).
WEATHER_RISK_WEIGHTS: dict[WeatherCondition, float] = {
    "seco": 1.0,
    "umido": 1.8,
    "molhado": 2.8,
}

# Coeficientes heurísticos do modelo logístico de consequência (docs/fisica.md Seção 5.2, Eq. 263):
# asfalto -> P(SC) ~10-20%; brita -> ~47-67%; muro -> ~62-79%.
LOGIT_SC_INTERCEPT = -1.2
RUNOFF_SC_LOGIT: dict[str, float] = {
    "asfalto": -0.7,
    "brita": 1.4,
    "muro": 2.0,
}
SEVERITY_SC_LOGIT: dict[str, float] = {
    "baixa": -0.3,
    "media": 0.0,
    "alta": 0.5,
}

# Probabilidade condicional de VSC dado que o incidente não gerou SC pleno.
RUNOFF_VSC_PROB_GIVEN_NO_SC: dict[str, float] = {
    "asfalto": 0.30,
    "brita": 0.65,
    "muro": 0.75,
}

# Duração típica em voltas de cada neutralização (docs/fisica.md Seção 5.4 [26]).
SC_DURATION_LAPS_RANGE = (2, 4)
VSC_DURATION_LAPS_RANGE = (1, 2)

# Fatores de ritmo e compressão de gaps sob neutralização.
SC_LAP_TIME_MULTIPLIER = 1.40
VSC_LAP_TIME_MULTIPLIER = 1.25
SC_COMPRESSED_GAP_AHEAD_S = 0.50


def _logistic(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


@dataclass(frozen=True)
class TrackSegmentRisk:
    """Segmento espacial 1D do circuito com sua intensidade integrada de incidente."""

    start_m: float
    end_m: float
    is_braking_zone: bool
    severity: str | None
    runoff: str
    corner_name: str | None
    weight_braking: float

    @property
    def length_m(self) -> float:
        return max(0.0, self.end_m - self.start_m)


@dataclass(frozen=True)
class RaceIncident:
    """Evento de incidente gerado estocasticamente em uma coordenada do circuito."""

    driver_id: str
    lap_number: int
    distance_m: float
    sector: int
    is_braking_zone: bool
    severity: str | None
    runoff: str
    corner_name: str | None
    consequence: IncidentConsequence
    time_loss_s: float
    caused_retirement: bool


def build_track_risk_profile(track_map: TrackMap) -> list[TrackSegmentRisk]:
    """Decompõe o circuito (Contrato D4) em segmentos de frenagem e trechos livres.

    Para cada `braking_zone`, associa a curva (`corner`) imediatamente adjacente ou
    sobreposta para enriquecer o evento com o nome real do ponto da pista
    (ex.: 'S do Senna', 'Bico de Pato', 'Variante della Roggia', 'Sainte Dévote').
    """
    braking_zones = sorted(
        (z for z in track_map.zones if z.type == "braking_zone" and z.length_m > 0),
        key=lambda z: z.start_m,
    )
    corners = [z for z in track_map.zones if z.type == "corner"]

    segments: list[TrackSegmentRisk] = []
    cursor_m = 0.0

    for bz in braking_zones:
        start_m = max(cursor_m, bz.start_m)
        end_m = min(float(track_map.length_m), bz.end_m)
        if start_m > cursor_m:
            segments.append(
                TrackSegmentRisk(
                    start_m=cursor_m,
                    end_m=start_m,
                    is_braking_zone=False,
                    severity=None,
                    runoff="asfalto",
                    corner_name=None,
                    weight_braking=1.0,
                )
            )
        if end_m > start_m:
            sev = str(bz.props.get("severity", "media")).lower()
            runoff = str(bz.props.get("runoff", "asfalto")).lower()
            w_brake = BRAKING_SEVERITY_WEIGHTS.get(sev, BRAKING_SEVERITY_WEIGHTS["media"])
            corner_name = _find_associated_corner_name(bz, corners)
            segments.append(
                TrackSegmentRisk(
                    start_m=start_m,
                    end_m=end_m,
                    is_braking_zone=True,
                    severity=sev,
                    runoff=runoff,
                    corner_name=corner_name,
                    weight_braking=w_brake,
                )
            )
            cursor_m = end_m

    if cursor_m < float(track_map.length_m):
        segments.append(
            TrackSegmentRisk(
                start_m=cursor_m,
                end_m=float(track_map.length_m),
                is_braking_zone=False,
                severity=None,
                runoff="asfalto",
                corner_name=None,
                weight_braking=1.0,
            )
        )

    return segments


def _find_associated_corner_name(braking_zone: Zone, corners: list[Zone]) -> str | None:
    """Localiza a curva cujo início está próximo ou sobreposto ao fim da zona de frenagem."""
    for c in corners:
        if abs(c.start_m - braking_zone.end_m) <= 60.0 or (
            c.start_m <= braking_zone.end_m and c.end_m >= braking_zone.start_m
        ):
            name = c.props.get("name")
            return str(name) if name else None
    return None


def incident_consequence_probabilities(
    runoff: str, severity: str | None
) -> tuple[float, float, float]:
    """Retorna (P_SC, P_VSC, P_TIME_LOSS) para um incidente dado `runoff` e `severity`.

    Usa a equação logística da Seção 5.2 de docs/fisica.md (Eq. 263).
    """
    r_key = runoff.lower()
    s_key = (severity or "baixa").lower()
    logit = (
        LOGIT_SC_INTERCEPT
        + RUNOFF_SC_LOGIT.get(r_key, RUNOFF_SC_LOGIT["asfalto"])
        + SEVERITY_SC_LOGIT.get(s_key, 0.0)
    )
    p_sc = _logistic(logit)
    p_vsc_cond = RUNOFF_VSC_PROB_GIVEN_NO_SC.get(r_key, 0.30)
    p_vsc = (1.0 - p_sc) * p_vsc_cond
    p_time_loss = max(0.0, 1.0 - p_sc - p_vsc)
    return p_sc, p_vsc, p_time_loss


def sample_driver_lap_incident(
    driver_id: str,
    lap_number: int,
    track_map: TrackMap,
    rng: random.Random,
    *,
    grip_factor: float = 1.0,
    weather: WeatherCondition = "seco",
    aggression: float = 0.5,
    base_intensity_per_m: float = BASE_INCIDENT_INTENSITY_PER_M,
) -> RaceIncident | None:
    """Amostra o Processo de Poisson Não-Homogêneo (NHPP) de um piloto ao longo de 1 volta.

    Equação (docs/fisica.md Seção 5.1):
        Lambda_volta = sum_i (lambda_base * w_braking,i * w_grip * w_weather * w_agg * L_i)
        P(incidente na volta) = 1 - exp(-Lambda_volta)

    Se ocorrer incidente, o segmento espacial exato é sorteado com probabilidade
    proporcional a Lambda_i, concentrando os incidentes nas `braking_zone` de alta
    severidade, e a consequência (SC, VSC ou TIME_LOSS) é decidida pelo `runoff`.
    """
    if grip_factor <= 0.0 or grip_factor > 1.0:
        raise ValueError("grip_factor deve estar em (0.0, 1.0]")
    if not (0.0 <= aggression <= 1.0):
        raise ValueError("aggression deve estar em [0.0, 1.0]")
    if weather not in WEATHER_RISK_WEIGHTS:
        raise ValueError(f"clima desconhecido: {weather}")

    segments = build_track_risk_profile(track_map)
    if not segments:
        return None

    # Multiplicadores globais do piloto/ambiente na volta
    w_grip = (1.0 / max(grip_factor, 0.30)) ** 1.5
    w_weather = WEATHER_RISK_WEIGHTS[weather]
    w_aggression = 0.7 + 0.6 * aggression

    common_mult = base_intensity_per_m * w_grip * w_weather * w_aggression
    segment_hazards = [common_mult * seg.weight_braking * seg.length_m for seg in segments]
    total_hazard = sum(segment_hazards)

    p_incident = 1.0 - math.exp(-total_hazard)
    if rng.random() >= p_incident:
        return None

    # Sorteia o segmento proporcionalmente à intensidade integrada Lambda_i
    threshold = rng.uniform(0.0, total_hazard)
    accum = 0.0
    chosen_seg = segments[-1]
    for seg, haz in zip(segments, segment_hazards, strict=True):
        accum += haz
        if threshold <= accum:
            chosen_seg = seg
            break

    distance_m = rng.uniform(chosen_seg.start_m, chosen_seg.end_m)
    sector = track_map.get_active_sector(distance_m)

    # Sorteia a consequência com base no runoff e na severidade da zona
    p_sc, p_vsc, _ = incident_consequence_probabilities(chosen_seg.runoff, chosen_seg.severity)
    u_cons = rng.random()
    if u_cons < p_sc:
        consequence: IncidentConsequence = "SC"
        time_loss_s = rng.uniform(12.0, 25.0)
        # Impactos que exigem SC em muro ou brita frequentemente causam abandono (DNF)
        retire_prob = 0.75 if chosen_seg.runoff in ("muro", "brita") else 0.45
        caused_retirement = rng.random() < retire_prob
    elif u_cons < p_sc + p_vsc:
        consequence = "VSC"
        time_loss_s = rng.uniform(6.0, 14.0)
        caused_retirement = rng.random() < 0.25
    else:
        consequence = "TIME_LOSS"
        time_loss_s = rng.uniform(2.5, 7.0)
        caused_retirement = False

    return RaceIncident(
        driver_id=driver_id,
        lap_number=lap_number,
        distance_m=round(distance_m, 1),
        sector=sector,
        is_braking_zone=chosen_seg.is_braking_zone,
        severity=chosen_seg.severity,
        runoff=chosen_seg.runoff,
        corner_name=chosen_seg.corner_name,
        consequence=consequence,
        time_loss_s=round(time_loss_s, 3),
        caused_retirement=caused_retirement,
    )


# ---------------------------------------------------------------------------
# Máquina de Estados de Safety Car e VSC — docs/fisica.md Seção 5.2 e 5.4
# ---------------------------------------------------------------------------


@dataclass
class SafetyCarStateMachine:
    """Máquina de estados determinística para controle de bandeiras (GREEN, VSC, SC).

    Estados e Transições:
    - `GREEN`: Corrida em ritmo normal, DRS habilitado (após `laps_since_restart >= 1`).
    - `VSC`: Virtual Safety Car. Acionado por incidente moderado; dura 1–2 voltas,
      multiplica os tempos de volta por 1.25 e mantém os gaps relativos.
    - `SC`: Safety Car pleno. Acionado por incidente severo (ou escalado a partir de VSC);
      dura 2–4 voltas, multiplica os tempos de volta por 1.40 e comprime o pelotão
      (`gap_to_ahead = 0.5 s` entre carros consecutivos).
    - Retomada (`SC/VSC -> GREEN`): Quando `laps_remaining` chega a 0 no fim da volta,
      retorna para `GREEN` e zera `laps_since_restart` (bloqueando o DRS na primeira
      volta de relargada após SC).
    """

    state: RaceControlState = "GREEN"
    laps_remaining: int = 0
    laps_since_restart: int = 2
    sc_deployments: int = 0
    vsc_deployments: int = 0

    def trigger_from_incidents(
        self, incidents: list[RaceIncident], rng: random.Random
    ) -> RaceControlState:
        """Avalia os incidentes ocorridos na volta e executa transição de estado se necessário."""
        has_sc = any(inc.consequence == "SC" for inc in incidents)
        has_vsc = any(inc.consequence == "VSC" for inc in incidents)

        if has_sc and self.state != "SC":
            self.state = "SC"
            self.laps_remaining = rng.randint(*SC_DURATION_LAPS_RANGE)
            self.sc_deployments += 1
        elif has_vsc and self.state == "GREEN":
            self.state = "VSC"
            self.laps_remaining = rng.randint(*VSC_DURATION_LAPS_RANGE)
            self.vsc_deployments += 1

        return self.state

    def advance_lap(self) -> RaceControlState:
        """Avança 1 volta na máquina de estados, tratando a contagem regressiva e relargada."""
        if self.state in ("SC", "VSC"):
            self.laps_remaining = max(0, self.laps_remaining - 1)
            if self.laps_remaining == 0:
                was_sc = self.state == "SC"
                self.state = "GREEN"
                # Regra FIA (docs/fisica.md Seção 4.3): após SC pleno, o DRS fica
                # desabilitado na volta imediata de relargada (laps_since_restart = 0).
                self.laps_since_restart = 0 if was_sc else 1
        else:
            self.laps_since_restart += 1

        return self.state

    @property
    def pace_multiplier(self) -> float:
        """Multiplicador de tempo de volta imposto pelo estado atual da direção de prova."""
        if self.state == "SC":
            return SC_LAP_TIME_MULTIPLIER
        if self.state == "VSC":
            return VSC_LAP_TIME_MULTIPLIER
        return 1.0

    @staticmethod
    def compress_gaps(
        positions: list[int], gap_per_position_s: float = SC_COMPRESSED_GAP_AHEAD_S
    ) -> list[tuple[float, float | None]]:
        """Calcula `(gap_to_leader, gap_to_ahead)` comprimidos em fila indiana sob Safety Car.

        Args:
            positions: Lista ordenada de posições (1..N) dos carros ativos.
            gap_per_position_s: Espaçamento temporal (s) entre carros consecutivos na fila.

        Returns:
            Lista de tuplas `(gap_to_leader, gap_to_ahead)` na mesma ordem de `positions`.
        """
        result: list[tuple[float, float | None]] = []
        for idx in range(len(positions)):
            if idx == 0:
                result.append((0.0, None))
            else:
                result.append((round(idx * gap_per_position_s, 3), round(gap_per_position_s, 3)))
        return result
