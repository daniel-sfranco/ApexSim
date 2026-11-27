"""backend/strategy/monte_carlo.py

Otimizador estocástico de estratégia de pit stop por Monte Carlo (Degrau 2 — Marco M4).
Simula K cenários futuros sob incerteza de degradação, tempo de parada e ocorrência
de Safety Car para selecionar o momento e o composto ideais, preservando o contrato
do Degrau 1 (`PitStrategyHeuristic.evaluate_driver -> PitDecision`).
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sim.weather import (
    DEFAULT_TRANSITION_PROBABILITIES,
    WEATHER_COMPOUND_TIME_PENALTIES,
    WeatherState,
    normalize_weather_state,
)

try:
    from strategy.config import (
        DEFAULT_PIT_STOP_DURATION,
        DEFAULT_WARMUP_PENALTY,
        MC_DEFAULT_SCENARIOS,
        MC_DEG_NOISE_STD,
        MC_HORIZON_LAPS,
        MC_MIN_TYRE_AGE_FOR_ROLLOUT,
        MC_PIT_DURATION_STD,
        MC_SC_PROB_PER_LAP,
        SAFETY_CAR_COST_FACTOR,
        UNDERCUT_GAP_THRESHOLD,
        UNDERCUT_MIN_AGE,
    )
    from strategy.heuristic import PitDecision, PitStrategyHeuristic
except ImportError:
    from .config import (
        DEFAULT_PIT_STOP_DURATION,
        DEFAULT_WARMUP_PENALTY,
        MC_DEFAULT_SCENARIOS,
        MC_DEG_NOISE_STD,
        MC_HORIZON_LAPS,
        MC_MIN_TYRE_AGE_FOR_ROLLOUT,
        MC_PIT_DURATION_STD,
        MC_SC_PROB_PER_LAP,
        SAFETY_CAR_COST_FACTOR,
        UNDERCUT_GAP_THRESHOLD,
        UNDERCUT_MIN_AGE,
    )
    from .heuristic import PitDecision, PitStrategyHeuristic

_RISK_AVERSION_WEIGHT: float = 0.20
_DRY_COMPOUNDS: tuple[str, ...] = ("soft", "medium", "hard")


@dataclass(frozen=True)
class StrategyCandidate:
    """Candidato de ação estratégica avaliado nos K cenários de Monte Carlo.

    Attributes:
        pit_offset: 0 para parar nesta volta, > 0 para parar daqui a `pit_offset`
            voltas, ou None para permanecer na pista (`STAY_OUT`).
        target_compound: Composto avaliado ("soft", "medium", "hard", "wet") ou None.
        expected_cost_s: Perda de tempo média (s) nos K cenários simulados.
        std_cost_s: Desvio-padrão (s) da perda de tempo nos K cenários.
        score_s: Pontuação final ponderada pelo perfil de risco (menor é melhor).
    """

    pit_offset: int | None
    target_compound: str | None
    expected_cost_s: float
    std_cost_s: float
    score_s: float


@dataclass(frozen=True)
class MonteCarloPlan:
    """Plano completo retornado pela otimização estocástica por Monte Carlo.

    Attributes:
        decision: Decisão final no contrato padrão do motor (`PitDecision`).
        optimal_pit_lap: Volta ótima estimada para a parada (`current_lap` se
            `should_pit=True`, `current_lap + best_offset` se prevista no horizonte,
            ou None).
        best_compound: Melhor composto identificado para o próximo stint.
        candidates: Tupla ordenada por `score_s` com os candidatos avaliados.
        num_scenarios: Quantidade K de cenários simulados (0 se via camada reativa).
    """

    decision: PitDecision
    optimal_pit_lap: int | None
    best_compound: str | None
    candidates: tuple[StrategyCandidate, ...]
    num_scenarios: int


def _extract_field(obj: Any, key: str, default: Any = None) -> Any:
    """Extrai um campo de dict ou objeto/dataclass de forma agnóstica."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _summarize_costs(
    cost_sum: float, cost_sq_sum: float, k: int, risk_weight: float
) -> tuple[float, float, float]:
    """Calcula média, desvio-padrão populacional e score ponderado pelo risco."""
    mean = cost_sum / k
    variance = max(0.0, (cost_sq_sum / k) - (mean * mean))
    std = math.sqrt(variance)
    score = mean + risk_weight * std
    return mean, std, score


class MonteCarloStrategyOptimizer(PitStrategyHeuristic):
    """Otimizador estocástico de estratégias de pit stop baseado em Monte Carlo."""

    def __init__(
        self,
        team_aggression: dict[str, float] | None = None,
        num_scenarios: int = MC_DEFAULT_SCENARIOS,
        horizon_laps: int = MC_HORIZON_LAPS,
        sc_prob_per_lap: float = MC_SC_PROB_PER_LAP,
        deg_noise_std: float = MC_DEG_NOISE_STD,
        pit_duration_std: float = MC_PIT_DURATION_STD,
        min_tyre_age_for_rollout: int = MC_MIN_TYRE_AGE_FOR_ROLLOUT,
        seed: int = 42,
        dynamic_weather: bool = False,
        weather_transition_probs: dict[WeatherState, dict[WeatherState, float]] | None = None,
    ) -> None:
        """Inicializa o otimizador de Monte Carlo com gerador pseudoaleatório próprio.

        Args:
            team_aggression: Mapa equipe -> agressividade em [0.0, 1.0].
            num_scenarios: Quantidade K de cenários futuros amostrados.
            horizon_laps: Horizonte máximo (voltas) para projeção de custo.
            sc_prob_per_lap: Probabilidade por volta de ocorrer Safety Car/VSC.
            deg_noise_std: Desvio-padrão relativo do multiplicador de degradação.
            pit_duration_std: Desvio-padrão (s) do tempo estacionário de parada.
            min_tyre_age_for_rollout: Idade mínima (voltas) para acionar rollouts em verde.
            seed: Semente determinística exclusiva deste otimizador.
            dynamic_weather: Quando True, simula transições climáticas via Cadeia de
                Markov (`sim.weather`) nos K cenários futuros.
            weather_transition_probs: Matriz de transição climática opcional (usa
                `DEFAULT_TRANSITION_PROBABILITIES` se omitida).
        """
        if num_scenarios < 1:
            raise ValueError("num_scenarios deve ser >= 1")
        if horizon_laps < 1:
            raise ValueError("horizon_laps deve ser >= 1")
        if sc_prob_per_lap < 0.0 or sc_prob_per_lap > 1.0:
            raise ValueError("sc_prob_per_lap deve estar em [0.0, 1.0]")
        if deg_noise_std < 0.0:
            raise ValueError("deg_noise_std deve ser >= 0.0")
        if pit_duration_std < 0.0:
            raise ValueError("pit_duration_std deve ser >= 0.0")
        if min_tyre_age_for_rollout < 0:
            raise ValueError("min_tyre_age_for_rollout deve ser >= 0")

        super().__init__(team_aggression=team_aggression)
        self.num_scenarios = int(num_scenarios)
        self.horizon_laps = int(horizon_laps)
        self.sc_prob_per_lap = float(sc_prob_per_lap)
        self.deg_noise_std = float(deg_noise_std)
        self.pit_duration_std = float(pit_duration_std)
        self.min_tyre_age_for_rollout = int(min_tyre_age_for_rollout)
        self.seed = int(seed)
        self.rng = random.Random(self.seed)
        self.dynamic_weather = bool(dynamic_weather)
        self.weather_transition_probs = weather_transition_probs or DEFAULT_TRANSITION_PROBABILITIES
        self._weather_cdf: dict[WeatherState, tuple[tuple[WeatherState, float], ...]] = (
            self._build_weather_cdf(self.weather_transition_probs)
        )

    @staticmethod
    def _build_weather_cdf(
        probs: dict[WeatherState, dict[WeatherState, float]],
    ) -> dict[WeatherState, tuple[tuple[WeatherState, float], ...]]:
        """Pré-computa CDF acumulada por estado para amostragem rápida na cadeia de Markov."""
        cdf: dict[WeatherState, tuple[tuple[WeatherState, float], ...]] = {}
        for state, row in probs.items():
            total = sum(row.values())
            acc = 0.0
            entries: list[tuple[WeatherState, float]] = []
            for next_state, weight in row.items():
                acc += weight / total if total > 0.0 else 0.0
                entries.append((next_state, acc))
            cdf[state] = tuple(entries)
        return cdf

    def _sample_next_weather(self, current: WeatherState) -> WeatherState:
        """Amostra o próximo estado climático da cadeia de Markov usando `self.rng`."""
        u = self.rng.random()
        entries = self._weather_cdf[current]
        for next_state, threshold in entries:
            if u <= threshold:
                return next_state
        return entries[-1][0]

    def _candidate_compounds(
        self, current_compound: str, laps_remaining: int, weather: str
    ) -> list[str]:
        """Retorna compostos válidos respeitando clima (seco/úmido/molhado) e regra FIA."""
        norm_weather = self._normalize_weather(weather)
        if norm_weather == "wet":
            return ["wet"]
        if norm_weather == "damp":
            return ["intermediate"]

        preferred = self._select_target_compound(current_compound, laps_remaining, norm_weather)
        allowed = [c for c in _DRY_COMPOUNDS if c != current_compound]
        if preferred in allowed:
            return [preferred] + [c for c in allowed if c != preferred]
        return allowed

    def _compound_stint_mismatch_penalty(
        self,
        compound: str,
        current_compound: str,
        laps_remaining: int,
        weather: str = "dry",
    ) -> float:
        """Penaliza compostos inadequados ao comprimento restante do stint e ao clima.

        Evita que horizontes curtos privilegiem pneus macios quando faltam dezenas
        de voltas (risco de cliff / parada extra) ou pneus duros em sprints finais.
        Retorna 0.0 para o composto ideal segundo a regra de durabilidade.
        """
        norm_weather = self._normalize_weather(weather)
        if norm_weather == "wet":
            return 0.0 if compound == "wet" else 50.0
        if norm_weather == "damp":
            return 0.0 if compound == "intermediate" else 50.0

        preferred = self._select_target_compound(current_compound, laps_remaining, norm_weather)
        if compound == preferred:
            return 0.0

        if compound == "soft":
            excess = max(0, laps_remaining - 20)
            return 6.0 + 0.50 * excess
        if compound == "medium":
            excess = max(0, laps_remaining - 30)
            return 6.0 + 0.35 * excess
        if compound == "hard":
            deficit = max(0, 30 - laps_remaining)
            return 6.0 + 0.25 * deficit
        return 6.0

    def _any_future_pit_beats_stay(
        self,
        current_compound: str,
        tyre_age: int,
        laps_remaining: int,
        weather: str,
        adjusted_pit_cost: float,
        get_deg: Callable[[str, int], float],
    ) -> bool:
        """Verifica se parar em alguma volta futura vence ficar até o fim da prova."""
        if laps_remaining <= 2:
            return False

        stay_all = sum(
            get_deg(current_compound, tyre_age + step) for step in range(1, laps_remaining + 1)
        )
        for offset in range(2, laps_remaining - 1, 2):
            rem_after = laps_remaining - offset
            target = self._select_target_compound(current_compound, rem_after, weather)
            cost_before = sum(
                get_deg(current_compound, tyre_age + step) for step in range(1, offset + 1)
            )
            cost_after = sum(get_deg(target, step) for step in range(1, rem_after + 1))
            if cost_before + cost_after + adjusted_pit_cost < stay_all:
                return True
        return False

    def _build_reactive_plan(
        self,
        should_pit: bool,
        target_compound: str | None,
        reason: str,
        current_lap: int,
        best_compound: str | None = None,
    ) -> MonteCarloPlan:
        """Constrói um MonteCarloPlan para decisões imediatas das camadas reativas."""
        decision = PitDecision(
            should_pit=should_pit,
            target_compound=target_compound if should_pit else None,
            reason=reason,
        )
        optimal_lap = current_lap if should_pit else None
        candidates: tuple[StrategyCandidate, ...] = ()
        if should_pit and target_compound is not None:
            candidates = (
                StrategyCandidate(
                    pit_offset=0,
                    target_compound=target_compound,
                    expected_cost_s=0.0,
                    std_cost_s=0.0,
                    score_s=0.0,
                ),
            )
        return MonteCarloPlan(
            decision=decision,
            optimal_pit_lap=optimal_lap,
            best_compound=best_compound if best_compound is not None else target_compound,
            candidates=candidates,
            num_scenarios=0,
        )

    def _simulate_scenarios(
        self,
        compound: str,
        tyre_age: int,
        laps_remaining: int,
        horizon: int,
        weather: str,
        pit_lane_loss_s: float,
        aggression: float,
        is_sc_pit_window: bool,
        candidates_compounds: list[str],
        preferred_compound: str,
        offsets: list[int],
        get_deg: Callable[[str, int], float],
        use_dynamic_weather: bool = False,
    ) -> tuple[StrategyCandidate, list[StrategyCandidate], list[StrategyCandidate]]:
        """Executa K rollouts com Common Random Numbers (CRN) para todos os candidatos."""
        aggression_factor = 1.25 - (0.50 * aggression)
        min_sc_age = self._min_sc_tyre_age(compound, aggression)
        is_in_sc_window = is_sc_pit_window and tyre_age >= min_sc_age
        eff_pit_loss = (
            pit_lane_loss_s * SAFETY_CAR_COST_FACTOR if is_sc_pit_window else pit_lane_loss_s
        )

        # Pré-cálculo determinístico sobre o horizonte H e janela estendida W
        base_stay_h = sum(get_deg(compound, tyre_age + s) for s in range(1, horizon + 1))
        base_fresh_h = {
            c: sum(get_deg(c, s) for s in range(1, horizon + 1)) for c in candidates_compounds
        }
        mismatch = {
            c: self._compound_stint_mismatch_penalty(c, compound, laps_remaining, weather)
            for c in candidates_compounds
        }

        offset_deg_delta: dict[int, float] = {}
        if offsets:
            max_offset = max(offsets)
            eval_w = min(laps_remaining, horizon + max_offset)
            base_pit_w_0 = sum(get_deg(preferred_compound, s) for s in range(1, eval_w + 1))
            for d in offsets:
                cost_w_d = sum(get_deg(compound, tyre_age + s) for s in range(1, d + 1)) + sum(
                    get_deg(preferred_compound, s) for s in range(1, eval_w - d + 1)
                )
                offset_deg_delta[d] = cost_w_d - base_pit_w_0

        # Acumuladores de custo e quadrado do custo nos K cenários
        stay_sum = 0.0
        stay_sq = 0.0
        pit_now_sum = {c: 0.0 for c in candidates_compounds}
        pit_now_sq = {c: 0.0 for c in candidates_compounds}
        offset_sum = {d: 0.0 for d in offsets}
        offset_sq = {d: 0.0 for d in offsets}

        k_total = self.num_scenarios
        p_horizon = (
            1.0 - (1.0 - self.sc_prob_per_lap) ** horizon
            if not is_sc_pit_window and self.sc_prob_per_lap > 0.0 and horizon > 1
            else 0.0
        )
        base_overhead = DEFAULT_PIT_STOP_DURATION + DEFAULT_WARMUP_PENALTY
        sc_savings_base = pit_lane_loss_s * (1.0 - SAFETY_CAR_COST_FACTOR) * aggression_factor
        start_weather_state: WeatherState = normalize_weather_state(weather, default="seco")

        for _ in range(k_total):
            deg_mult = (
                max(0.4, 1.0 + self.rng.gauss(0.0, self.deg_noise_std))
                if self.deg_noise_std > 0.0
                else 1.0
            )
            pit_noise = (
                max(-1.0, self.rng.gauss(0.0, self.pit_duration_std))
                if self.pit_duration_std > 0.0
                else 0.0
            )
            sc_lap: int | None = None
            if p_horizon > 0.0 and self.rng.random() < p_horizon:
                sc_lap = self.rng.randint(1, horizon)

            if sc_lap is not None:
                sc_laps = min(2, horizon - sc_lap + 1)
                pace_scale = (horizon - 0.65 * sc_laps) / horizon
            else:
                pace_scale = 1.0

            deg_scale = deg_mult * pace_scale
            pit_cost_k = (eff_pit_loss + base_overhead + pit_noise) * aggression_factor
            full_pit_cost_k = (pit_lane_loss_s + base_overhead + pit_noise) * aggression_factor

            # Evolução climática estocástica via Cadeia de Markov (sim/weather.py)
            weather_stay_pen = 0.0
            weather_fresh_pen = {c: 0.0 for c in candidates_compounds}
            early_weather_crossover = False
            if use_dynamic_weather:
                w_curr = start_weather_state
                for step in range(1, horizon + 1):
                    w_curr = self._sample_next_weather(w_curr)
                    pen_row = WEATHER_COMPOUND_TIME_PENALTIES[w_curr]
                    weather_stay_pen += pen_row.get(compound, 0.0)
                    for c in candidates_compounds:
                        weather_fresh_pen[c] += pen_row.get(c, 0.0)
                    if (
                        not early_weather_crossover
                        and step <= 4
                        and (
                            (start_weather_state == "seco" and w_curr != "seco")
                            or (start_weather_state != "seco" and w_curr == "seco")
                        )
                    ):
                        early_weather_crossover = True

            # 1) STAY_OUT
            cost_stay_k = deg_scale * base_stay_h + weather_stay_pen
            if sc_lap is not None and sc_lap <= 2:
                cost_stay_k -= sc_savings_base
            if is_in_sc_window:
                cost_stay_k += full_pit_cost_k
            stay_sum += cost_stay_k
            stay_sq += cost_stay_k * cost_stay_k

            # 2) PIT_NOW para cada composto válido
            # Se o clima virar nos próximos 4 giros, parar agora força uma 2ª parada imediata
            extra_crossover_stop = full_pit_cost_k if early_weather_crossover else 0.0
            for c in candidates_compounds:
                cost_c_k = (
                    deg_scale * base_fresh_h[c]
                    + weather_fresh_pen[c]
                    + pit_cost_k
                    + extra_crossover_stop
                    + mismatch[c]
                )
                pit_now_sum[c] += cost_c_k
                pit_now_sq[c] += cost_c_k * cost_c_k

            # 3) Offsets futuros representativos
            base_pref_deg = deg_scale * base_fresh_h[preferred_compound]
            pref_weather_pen = weather_fresh_pen[preferred_compound]
            for d in offsets:
                if sc_lap is not None and sc_lap <= d:
                    pit_d_k = (
                        pit_lane_loss_s * SAFETY_CAR_COST_FACTOR + base_overhead + pit_noise
                    ) * aggression_factor
                else:
                    pit_d_k = pit_cost_k
                cost_d_k = (
                    base_pref_deg + deg_scale * offset_deg_delta[d] + pref_weather_pen + pit_d_k
                )
                offset_sum[d] += cost_d_k
                offset_sq[d] += cost_d_k * cost_d_k

        # Converte somas em StrategyCandidate
        stay_mean, stay_std, stay_score = _summarize_costs(
            stay_sum, stay_sq, k_total, _RISK_AVERSION_WEIGHT
        )
        stay_cand = StrategyCandidate(
            pit_offset=None,
            target_compound=None,
            expected_cost_s=stay_mean,
            std_cost_s=stay_std,
            score_s=stay_score,
        )

        pit_now_cands: list[StrategyCandidate] = []
        for c in candidates_compounds:
            mean, std, score = _summarize_costs(
                pit_now_sum[c], pit_now_sq[c], k_total, _RISK_AVERSION_WEIGHT
            )
            pit_now_cands.append(
                StrategyCandidate(
                    pit_offset=0,
                    target_compound=c,
                    expected_cost_s=mean,
                    std_cost_s=std,
                    score_s=score,
                )
            )

        offset_cands: list[StrategyCandidate] = []
        for d in offsets:
            mean, std, score = _summarize_costs(
                offset_sum[d], offset_sq[d], k_total, _RISK_AVERSION_WEIGHT
            )
            offset_cands.append(
                StrategyCandidate(
                    pit_offset=d,
                    target_compound=preferred_compound,
                    expected_cost_s=mean,
                    std_cost_s=std,
                    score_s=score,
                )
            )

        return stay_cand, pit_now_cands, offset_cands

    def optimize_driver(
        self,
        driver_state: Any,
        race_state: Any,
        pit_lane_loss_s: float,
        degradation_curve: Callable[[str, int], float],
    ) -> MonteCarloPlan:
        """Executa o otimizador de Monte Carlo para um piloto e retorna o plano completo.

        Args:
            driver_state: Dict ou DriverState com dados do piloto.
            race_state: Dict ou RaceState com metadados da corrida.
            pit_lane_loss_s: Perda média estática no pit lane em segundos.
            degradation_curve: Função `(compound, age) -> perda em segundos`.

        Returns:
            MonteCarloPlan com decisão, volta ótima prevista e candidatos ordenados.
        """
        team = _extract_field(driver_state, "team", "Generic")
        aggression = self._get_aggression(team)

        compound_raw = _extract_field(driver_state, "tyre_compound", "medium")
        compound = (
            compound_raw.name.lower()
            if hasattr(compound_raw, "name")
            else str(compound_raw).lower()
        )
        if compound == "inter":
            compound = "intermediate"
        tyre_age = int(
            _extract_field(
                driver_state, "tyre_age", _extract_field(driver_state, "tyre_age_laps", 0)
            )
        )

        current_lap = int(
            _extract_field(
                race_state, "current_lap", _extract_field(driver_state, "current_lap", 1)
            )
        )
        total_laps = int(_extract_field(race_state, "total_laps", 50))
        laps_remaining = max(1, total_laps - current_lap)

        track_status = _extract_field(race_state, "track_status", "GREEN")
        track_status_str = (
            track_status.name if hasattr(track_status, "name") else str(track_status).upper()
        )
        weather = self._normalize_weather(_extract_field(race_state, "weather", "dry"))
        use_dynamic_weather = bool(
            _extract_field(race_state, "dynamic_weather", self.dynamic_weather)
        )
        target_compound = self._select_target_compound(compound, laps_remaining, weather)

        # Volta final sem interrupção
        if laps_remaining <= 1 and track_status_str != "RED":
            return self._build_reactive_plan(False, None, "STAY_OUT", current_lap, target_compound)

        # Prioridade 1: Bandeira Vermelha (parada gratuita)
        if (
            track_status_str == "RED" or _extract_field(race_state, "red_flag", False)
        ) and tyre_age > 1:
            return self._build_reactive_plan(True, target_compound, "RED_FLAG", current_lap)

        # Prioridade 2: Crossover Climático (seco <-> úmido <-> molhado)
        is_slick = compound in _DRY_COMPOUNDS
        if weather == "wet":
            if is_slick or (compound == "intermediate" and laps_remaining > 5):
                return self._build_reactive_plan(True, "wet", "WEATHER", current_lap)
        elif weather == "damp":
            if is_slick or (compound == "wet" and laps_remaining > 6):
                return self._build_reactive_plan(True, "intermediate", "WEATHER", current_lap)
        elif weather == "dry" and not is_slick:
            target_dry = self._select_target_compound(compound, laps_remaining, "dry")
            return self._build_reactive_plan(True, target_dry, "WEATHER", current_lap)

        is_sc = track_status_str in ("SAFETY_CAR", "VSC") or bool(
            _extract_field(race_state, "safety_car", False)
        )
        is_sc_pit_window = is_sc and is_slick and laps_remaining > 3

        # Prioridade 3 (Safety Car) vai ao rollout;
        # Prioridade 4 (Undercut) tem precedência fora de SC
        rival_behind_pitted = bool(_extract_field(driver_state, "rival_behind_pitted", False))
        gap_behind = _extract_field(driver_state, "gap_to_car_behind", None)
        is_undercut_threat = (
            rival_behind_pitted
            and gap_behind is not None
            and gap_behind <= UNDERCUT_GAP_THRESHOLD
            and tyre_age >= UNDERCUT_MIN_AGE
            and laps_remaining > 5
        )

        if not is_sc_pit_window and is_undercut_threat:
            return self._build_reactive_plan(True, target_compound, "UNDERCUT", current_lap)

        if laps_remaining <= 2:
            return self._build_reactive_plan(False, None, "STAY_OUT", current_lap, target_compound)

        # Filtro rápido em início de stint sob bandeira verde
        if not is_sc_pit_window and tyre_age < self.min_tyre_age_for_rollout:
            return self._build_reactive_plan(False, None, "STAY_OUT", current_lap, target_compound)

        horizon = min(laps_remaining, self.horizon_laps)
        deg_cache: dict[tuple[str, int], float] = {}

        def get_deg(comp: str, age: int) -> float:
            key = (comp, age)
            val = deg_cache.get(key)
            if val is None:
                val = float(degradation_curve(comp, age))
                deg_cache[key] = val
            return val

        candidates_compounds = self._candidate_compounds(compound, laps_remaining, weather)
        max_offset = min(horizon, laps_remaining - 2)
        offsets = list(range(2, max_offset + 1, 2)) if max_offset >= 2 else []

        stay_cand, pit_now_cands, offset_cands = self._simulate_scenarios(
            compound=compound,
            tyre_age=tyre_age,
            laps_remaining=laps_remaining,
            horizon=horizon,
            weather=weather,
            pit_lane_loss_s=pit_lane_loss_s,
            aggression=aggression,
            is_sc_pit_window=is_sc_pit_window,
            candidates_compounds=candidates_compounds,
            preferred_compound=target_compound,
            offsets=offsets,
            get_deg=get_deg,
            use_dynamic_weather=use_dynamic_weather,
        )

        best_pit_now = min(pit_now_cands, key=lambda c: c.score_s)
        all_candidates = sorted([stay_cand, *pit_now_cands, *offset_cands], key=lambda c: c.score_s)

        # Se sob SC o rollout não disparou parada, ainda responde à ameaça de undercut
        should_pit_now = best_pit_now.score_s < stay_cand.score_s
        if should_pit_now:
            reason = "SAFETY_CAR" if is_sc_pit_window else "DEGRADATION"
            chosen_comp = best_pit_now.target_compound or target_compound
            return MonteCarloPlan(
                decision=PitDecision(should_pit=True, target_compound=chosen_comp, reason=reason),
                optimal_pit_lap=current_lap,
                best_compound=chosen_comp,
                candidates=tuple(all_candidates),
                num_scenarios=self.num_scenarios,
            )

        if is_sc_pit_window and is_undercut_threat:
            return self._build_reactive_plan(True, target_compound, "UNDERCUT", current_lap)

        # Não para agora: estima melhor volta futura no horizonte caso parada futura valha a pena
        aggression_factor = 1.25 - (0.50 * aggression)
        nominal_pit_cost = (
            pit_lane_loss_s + DEFAULT_PIT_STOP_DURATION + DEFAULT_WARMUP_PENALTY
        ) * aggression_factor
        optimal_pit_lap: int | None = None
        best_future_compound = best_pit_now.target_compound or target_compound

        if offset_cands and self._any_future_pit_beats_stay(
            compound, tyre_age, laps_remaining, weather, nominal_pit_cost, get_deg
        ):
            best_offset_cand = min(offset_cands, key=lambda c: c.score_s)
            if best_offset_cand.pit_offset is not None:
                optimal_pit_lap = current_lap + best_offset_cand.pit_offset
                if best_offset_cand.target_compound is not None:
                    best_future_compound = best_offset_cand.target_compound

        return MonteCarloPlan(
            decision=PitDecision(should_pit=False, target_compound=None, reason="STAY_OUT"),
            optimal_pit_lap=optimal_pit_lap,
            best_compound=best_future_compound,
            candidates=tuple(all_candidates),
            num_scenarios=self.num_scenarios,
        )

    def evaluate_driver(
        self,
        driver_state: Any,
        race_state: Any,
        pit_lane_loss_s: float,
        degradation_curve: Callable[[str, int], float],
    ) -> PitDecision:
        """Avalia o estado do piloto via Monte Carlo e retorna a decisão no contrato D1."""
        return self.optimize_driver(
            driver_state=driver_state,
            race_state=race_state,
            pit_lane_loss_s=pit_lane_loss_s,
            degradation_curve=degradation_curve,
        ).decision
