"""backend/strategy/heuristic.py

Heurística de estratégia de pit stop para o ApexSim.
Combina o algoritmo base de custo-benefício com sobrelay de regras reativas.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

try:
    from strategy.config import (
        DEFAULT_AGGRESSION,
        DEFAULT_HORIZON,
        DEFAULT_PIT_STOP_DURATION,
        DEFAULT_TEAM_AGGRESSION,
        DEFAULT_WARMUP_PENALTY,
        SAFETY_CAR_COST_FACTOR,
        UNDERCUT_GAP_THRESHOLD,
        UNDERCUT_MIN_AGE,
    )
except ImportError:
    from .config import (
        DEFAULT_AGGRESSION,
        DEFAULT_HORIZON,
        DEFAULT_PIT_STOP_DURATION,
        DEFAULT_TEAM_AGGRESSION,
        DEFAULT_WARMUP_PENALTY,
        SAFETY_CAR_COST_FACTOR,
        UNDERCUT_GAP_THRESHOLD,
        UNDERCUT_MIN_AGE,
    )


@dataclass
class PitDecision:
    """Decisão emitida pelo avaliador de estratégia de pit stop.

    Attributes:
        should_pit: Indica se o piloto deve realizar o pit stop na próxima volta.
        target_compound: Composto sugerido ("soft", "medium", "hard", "wet").
        reason: Motivo da decisão ("DEGRADATION", "SAFETY_CAR", "RED_FLAG",
                "UNDERCUT", "WEATHER", "STAY_OUT").
    """

    should_pit: bool
    target_compound: str | None = None
    reason: str = "STAY_OUT"


class PitStrategyHeuristic:
    """Avaliador heurístico de estratégias de pit stop."""

    def __init__(self, team_aggression: dict[str, float] | None = None):
        """Inicializa a heurística com o mapa de agressividade por equipe.

        Args:
            team_aggression: Dicionário mapeando nome da equipe para um float (0.0 a 1.0).
                             Ex: {"Ferrari": 0.8, "Red Bull": 0.9, "Haas": 0.2}
        """
        self.team_aggression = dict(DEFAULT_TEAM_AGGRESSION) if team_aggression is None else team_aggression

    def _get_aggression(self, team: str) -> float:
        """Obtém o nível de agressividade da equipe (default 0.5 se não especificado)."""
        return self.team_aggression.get(team, DEFAULT_AGGRESSION)

    def _select_target_compound(
        self, current_compound: str, laps_remaining: int, weather: str = "dry"
    ) -> str:
        """Seleciona o próximo composto com base no clima, voltas e regra FIA de alternância.

        Regras aplicadas (Passo 4):
        1. Se pista molhada: pneu de chuva ("wet").
        2. Se pista seca: escolhe a melhor durabilidade para as voltas restantes
           (<=15 soft, <=30 medium, >30 hard).
        3. Não repete o mesmo composto consecutivamente no seco (ex: troca Médio por Duro/Macio).
        """
        if weather == "wet":
            return "wet"

        # Janela de durabilidade ideal para voltas restantes
        if laps_remaining <= 15:
            preferred = "soft"
        elif laps_remaining <= 30:
            preferred = "medium"
        else:
            preferred = "hard"

        # Regra de alternância da FIA em corrida seca: não trocar para o mesmo composto
        if preferred == current_compound:
            if preferred == "medium":
                return "hard" if laps_remaining > 20 else "soft"
            elif preferred == "hard":
                return "medium"
            else:  # soft
                return "medium"

        return preferred

    def evaluate_driver(
        self,
        driver_state: Any,
        race_state: Any,
        pit_lane_loss_s: float,
        degradation_curve: Callable[[str, int], float],
    ) -> PitDecision:
        """Avalia o estado do piloto e decide se ele deve parar na próxima volta.

        Aplica as regras em cascata de prioridades:
        1. Bandeira Vermelha (parada gratuita)
        2. Crossover Climático (incompatibilidade pneu/pista)
        3. Safety Car / VSC (custo do pit reduzido em ~45%)
        4. Undercut Defensivo (rival imediatamente atrás parou com pneu novo)
        5. Algoritmo Base de Degradação (Prejuízo Acumulado > Custo Ajustado)

        Args:
            driver_state: Dict ou DriverState com dados do piloto.
            race_state: Dict ou RaceState com metadados da corrida.
            pit_lane_loss_s: Perda média estática no pit lane em segundos.
            degradation_curve: Função (compound, age) -> perda em segundos.

        Returns:
            PitDecision com decisão, composto alvo e justificativa.
        """

        # Extração agnóstica para suportar dict ou dataclasses DriverState/RaceState
        def get_d(key: str, default: Any = None) -> Any:
            if isinstance(driver_state, dict):
                return driver_state.get(key, default)
            return getattr(driver_state, key, default)

        def get_r(key: str, default: Any = None) -> Any:
            if isinstance(race_state, dict):
                return race_state.get(key, default)
            return getattr(race_state, key, default)

        team = get_d("team", "Generic")
        aggression = self._get_aggression(team)

        # Composto e idade atual
        compound_raw = get_d("tyre_compound", "medium")
        compound = (
            compound_raw.name.lower()
            if hasattr(compound_raw, "name")
            else str(compound_raw).lower()
        )
        tyre_age = int(get_d("tyre_age", get_d("tyre_age_laps", 0)))

        # Metadados de corrida
        current_lap = int(get_r("current_lap", get_d("current_lap", 1)))
        total_laps = int(get_r("total_laps", 50))
        laps_remaining = max(1, total_laps - current_lap)

        # Status de pista e clima
        track_status = get_r("track_status", "GREEN")
        track_status_str = (
            track_status.name if hasattr(track_status, "name") else str(track_status).upper()
        )
        weather = str(get_r("weather", "dry")).lower()

        # Seleção do composto alvo para a parada
        target_compound = self._select_target_compound(compound, laps_remaining, weather)

        # Se for a última volta e a corrida não estiver interrompida, nunca para
        if laps_remaining <= 1 and track_status_str != "RED":
            return PitDecision(should_pit=False, reason="STAY_OUT")

        # -------------------------------------------------------------------
        # Prioridade 1: Bandeira Vermelha (Parada gratuita nos boxes)
        # -------------------------------------------------------------------
        if track_status_str == "RED" or get_r("red_flag", False):
            # Se o pneu atual já não for novo (idade > 1), troca sem custo de tempo
            if tyre_age > 1:
                return PitDecision(
                    should_pit=True,
                    target_compound=target_compound,
                    reason="RED_FLAG",
                )

        # -------------------------------------------------------------------
        # Prioridade 2: Crossover Climático
        # -------------------------------------------------------------------
        is_slick = compound in ("soft", "medium", "hard")
        if weather == "wet" and is_slick:
            return PitDecision(should_pit=True, target_compound="wet", reason="WEATHER")
        if weather == "dry" and not is_slick:
            target_dry = self._select_target_compound(compound, laps_remaining, "dry")
            return PitDecision(should_pit=True, target_compound=target_dry, reason="WEATHER")

        # -------------------------------------------------------------------
        # Prioridade 3: Safety Car / VSC
        # -------------------------------------------------------------------
        is_sc = track_status_str in ("SAFETY_CAR", "VSC") or get_r("safety_car", False)
        if is_sc and is_slick and laps_remaining > 3:
            # Perda relativa de tempo cai para ~55% durante Safety Car
            sc_pit_loss = pit_lane_loss_s * SAFETY_CAR_COST_FACTOR
            sc_total_cost = sc_pit_loss + DEFAULT_PIT_STOP_DURATION + DEFAULT_WARMUP_PENALTY
            aggression_factor = 1.25 - (0.50 * aggression)
            sc_adjusted_cost = sc_total_cost * aggression_factor

            # Projeção de degradação com o custo reduzido
            horizon = min(laps_remaining, DEFAULT_HORIZON)
            loss_current = sum(
                degradation_curve(compound, tyre_age + k) for k in range(1, horizon + 1)
            )
            loss_fresh = sum(degradation_curve(target_compound, k) for k in range(1, horizon + 1))
            accumulated_loss = loss_current - loss_fresh

            # Pilotos na janela aproveitam o custo reduzido sob Safety Car
            min_sc_age = int(14 - (aggression * 6))  # 8 voltas p/ agressivo, 13 p/ conservador
            if accumulated_loss > sc_adjusted_cost or tyre_age >= min_sc_age:
                return PitDecision(
                    should_pit=True,
                    target_compound=target_compound,
                    reason="SAFETY_CAR",
                )

        # -------------------------------------------------------------------
        # Prioridade 4: Undercut Defensivo
        # -------------------------------------------------------------------
        rival_behind_pitted = get_d("rival_behind_pitted", False)
        gap_behind = get_d("gap_to_car_behind", None)

        if (
            rival_behind_pitted
            and gap_behind is not None
            and gap_behind <= UNDERCUT_GAP_THRESHOLD
            and tyre_age >= UNDERCUT_MIN_AGE
            and laps_remaining > 5
        ):
            return PitDecision(
                should_pit=True,
                target_compound=target_compound,
                reason="UNDERCUT",
            )

        # -------------------------------------------------------------------
        # Prioridade 5: Algoritmo Base de Degradação (Custo x Benefício)
        # -------------------------------------------------------------------
        if laps_remaining <= 2:
            return PitDecision(should_pit=False, reason="STAY_OUT")

        horizon = min(laps_remaining, DEFAULT_HORIZON)
        loss_current = sum(degradation_curve(compound, tyre_age + k) for k in range(1, horizon + 1))
        loss_fresh = sum(degradation_curve(target_compound, k) for k in range(1, horizon + 1))
        accumulated_degradation_loss = loss_current - loss_fresh

        total_pit_cost = pit_lane_loss_s + DEFAULT_PIT_STOP_DURATION + DEFAULT_WARMUP_PENALTY
        aggression_factor = 1.25 - (0.50 * aggression)
        adjusted_pit_cost = total_pit_cost * aggression_factor

        if accumulated_degradation_loss > adjusted_pit_cost:
            return PitDecision(
                should_pit=True,
                target_compound=target_compound,
                reason="DEGRADATION",
            )

        return PitDecision(should_pit=False, reason="STAY_OUT")
