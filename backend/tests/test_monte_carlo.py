"""Testes unitários, de sanidade e benchmark para o otimizador Monte Carlo (M4).

Cobre os critérios de aceite da M4:
1. Convergência com a heurística determinística (Degrau 1) em cenário simples.
2. Simulação de K cenários sob incerteza, ordenação de candidatos e determinismo por seed.
3. Preservação das camadas reativas (RED_FLAG, WEATHER, SAFETY_CAR, YELLOW, UNDERCUT).
4. Execução completa de corrida (20 carros x 55 voltas) mantida abaixo de 30 segundos.
"""

import time

import pytest

from sim.engine import RaceEngine
from sim.physics import tyre_time_loss
from sim.state import DriverState, PitStatus, RaceState, TrackStatus, TyreCompound
from sim.track import TrackMap
from strategy import (
    MonteCarloPlan,
    MonteCarloStrategyOptimizer,
    PitDecision,
    PitStrategyHeuristic,
    StrategyCandidate,
)

GRID_TEAMS: dict[str, float] = {
    "Red Bull": 0.9,
    "Ferrari": 0.8,
    "Mercedes": 0.7,
    "McLaren": 0.7,
    "Aston Martin": 0.5,
    "Alpine": 0.4,
    "Williams": 0.3,
    "Haas": 0.2,
    "Kick Sauber": 0.1,
    "RB": 0.5,
}


def _calc_deg(compound: str, age: int) -> float:
    return tyre_time_loss(compound, age, 35.0)


@pytest.fixture
def teams() -> dict[str, float]:
    return dict(GRID_TEAMS)


@pytest.fixture
def optimizer(teams: dict[str, float]) -> MonteCarloStrategyOptimizer:
    return MonteCarloStrategyOptimizer(team_aggression=teams, num_scenarios=64, seed=42)


# ===========================================================================
# 1. Teste de Sanidade: Convergência com PitStrategyHeuristic (Degrau 1)
# ===========================================================================


class TestMonteCarloSanityConvergence:
    def test_convergencia_com_heuristica_sem_incerteza_todas_equipes(
        self, teams: dict[str, float]
    ) -> None:
        """Com incerteza zerada, Monte Carlo converge exatamente com a heurística base."""
        heuristic = PitStrategyHeuristic(team_aggression=teams)
        mc_det = MonteCarloStrategyOptimizer(
            team_aggression=teams,
            num_scenarios=16,
            sc_prob_per_lap=0.0,
            deg_noise_std=0.0,
            pit_duration_std=0.0,
            seed=42,
        )

        for team in teams:
            h_comp, h_age, h_pits = "medium", 0, []
            m_comp, m_age, m_pits = "medium", 0, []

            for lap in range(1, 51):
                race = {
                    "current_lap": lap,
                    "total_laps": 50,
                    "track_status": "GREEN",
                    "weather": "dry",
                }
                h_age += 1
                m_age += 1

                dec_h = heuristic.evaluate_driver(
                    {
                        "team": team,
                        "tyre_compound": h_comp,
                        "tyre_age": h_age,
                        "current_lap": lap,
                    },
                    race,
                    21.0,
                    _calc_deg,
                )
                dec_m = mc_det.evaluate_driver(
                    {
                        "team": team,
                        "tyre_compound": m_comp,
                        "tyre_age": m_age,
                        "current_lap": lap,
                    },
                    race,
                    21.0,
                    _calc_deg,
                )

                assert dec_m.should_pit == dec_h.should_pit, f"Divergência em {team} volta {lap}"
                assert dec_m.reason == dec_h.reason

                if dec_h.should_pit:
                    h_pits.append((lap, dec_h.target_compound))
                    h_comp = dec_h.target_compound or h_comp
                    h_age = 0
                if dec_m.should_pit:
                    m_pits.append((lap, dec_m.target_compound))
                    m_comp = dec_m.target_compound or m_comp
                    m_age = 0

            assert m_pits == h_pits, f"Paradas divergentes para {team}: {m_pits} != {h_pits}"

    @pytest.mark.parametrize("start_compound", ["soft", "medium", "hard"])
    def test_convergencia_compostos_iniciais(
        self, teams: dict[str, float], start_compound: str
    ) -> None:
        """Convergência vale independentemente do composto inicial no stint."""
        heuristic = PitStrategyHeuristic(team_aggression=teams)
        mc_det = MonteCarloStrategyOptimizer(
            team_aggression=teams,
            num_scenarios=8,
            sc_prob_per_lap=0.0,
            deg_noise_std=0.0,
            pit_duration_std=0.0,
            seed=7,
        )
        h_comp, h_age, h_pits = start_compound, 0, []
        m_comp, m_age, m_pits = start_compound, 0, []

        for lap in range(1, 51):
            race = {"current_lap": lap, "total_laps": 50, "track_status": "GREEN", "weather": "dry"}
            h_age += 1
            m_age += 1
            dec_h = heuristic.evaluate_driver(
                {"team": "Ferrari", "tyre_compound": h_comp, "tyre_age": h_age, "current_lap": lap},
                race,
                21.0,
                _calc_deg,
            )
            dec_m = mc_det.evaluate_driver(
                {"team": "Ferrari", "tyre_compound": m_comp, "tyre_age": m_age, "current_lap": lap},
                race,
                21.0,
                _calc_deg,
            )
            if dec_h.should_pit:
                h_pits.append((lap, dec_h.target_compound))
                h_comp = dec_h.target_compound or h_comp
                h_age = 0
            if dec_m.should_pit:
                m_pits.append((lap, dec_m.target_compound))
                m_comp = dec_m.target_compound or m_comp
                m_age = 0

        assert m_pits == h_pits

    def test_convergencia_sob_safety_car_sem_incerteza(self, teams: dict[str, float]) -> None:
        """Sob Safety Car sem ruído, ambos disparam parada para o mesmo grupo de pilotos."""
        heuristic = PitStrategyHeuristic(team_aggression=teams)
        mc_det = MonteCarloStrategyOptimizer(
            team_aggression=teams,
            num_scenarios=8,
            sc_prob_per_lap=0.0,
            deg_noise_std=0.0,
            pit_duration_std=0.0,
            seed=42,
        )
        race_sc = {
            "current_lap": 20,
            "total_laps": 50,
            "track_status": "SAFETY_CAR",
            "weather": "dry",
        }
        for team in teams:
            for age in (3, 10, 15, 22):
                driver = {
                    "team": team,
                    "tyre_compound": "medium",
                    "tyre_age": age,
                    "current_lap": 20,
                }
                dec_h = heuristic.evaluate_driver(driver, race_sc, 21.0, _calc_deg)
                dec_m = mc_det.evaluate_driver(driver, race_sc, 21.0, _calc_deg)
                assert dec_m == dec_h, f"Divergência SC para {team}, age={age}: {dec_m} != {dec_h}"


# ===========================================================================
# 2. Otimização Estocástica sob Incerteza (K cenários) e Determinismo
# ===========================================================================


class TestMonteCarloStochasticOptimization:
    def test_optimize_driver_retorna_plano_e_candidatos_ordenados(
        self, optimizer: MonteCarloStrategyOptimizer
    ) -> None:
        """optimize_driver retorna K cenários, desvios-padrão > 0 e volta ótima prevista."""
        driver = {"team": "Ferrari", "tyre_compound": "medium", "tyre_age": 20, "current_lap": 20}
        race = {"current_lap": 20, "total_laps": 50, "track_status": "GREEN", "weather": "dry"}

        plan = optimizer.optimize_driver(driver, race, 21.0, _calc_deg)

        assert isinstance(plan, MonteCarloPlan)
        assert isinstance(plan.decision, PitDecision)
        assert plan.num_scenarios == 64
        assert len(plan.candidates) >= 3
        assert all(isinstance(c, StrategyCandidate) for c in plan.candidates)

        # Candidatos ordenados do menor para o maior score_s
        scores = [c.score_s for c in plan.candidates]
        assert scores == sorted(scores)
        assert any(c.std_cost_s > 0.0 for c in plan.candidates)

        # Na volta 20 ainda fica na pista, mas já prevê janela ótima realista
        assert plan.decision.should_pit is False
        assert plan.optimal_pit_lap is not None
        assert 22 <= plan.optimal_pit_lap <= 32
        assert plan.best_compound in ("soft", "hard")

    def test_sem_parada_futura_prevista_nos_ultimos_giros(
        self, optimizer: MonteCarloStrategyOptimizer
    ) -> None:
        """Faltando poucas voltas com pneu inteiro, não prevê parada futura."""
        driver = {"team": "Ferrari", "tyre_compound": "medium", "tyre_age": 12, "current_lap": 46}
        race = {"current_lap": 46, "total_laps": 50, "track_status": "GREEN", "weather": "dry"}

        plan = optimizer.optimize_driver(driver, race, 21.0, _calc_deg)
        assert plan.decision.should_pit is False
        assert plan.optimal_pit_lap is None

    def test_regra_fia_alternancia_de_composto_no_seco(
        self, optimizer: MonteCarloStrategyOptimizer
    ) -> None:
        """No seco, nunca sugere trocar para o mesmo composto atual."""
        for compound in ("soft", "medium", "hard"):
            driver = {
                "team": "Red Bull",
                "tyre_compound": compound,
                "tyre_age": 35,
                "current_lap": 35,
            }
            race = {"current_lap": 35, "total_laps": 55, "track_status": "GREEN", "weather": "dry"}
            plan = optimizer.optimize_driver(driver, race, 21.0, _calc_deg)
            assert plan.decision.should_pit is True
            assert plan.decision.target_compound != compound
            assert plan.decision.target_compound in ("soft", "medium", "hard")

    def test_determinismo_por_seed(self, teams: dict[str, float]) -> None:
        """Duas instâncias com a mesma seed geram planos e custos idênticos."""
        opt1 = MonteCarloStrategyOptimizer(team_aggression=teams, num_scenarios=64, seed=123)
        opt2 = MonteCarloStrategyOptimizer(team_aggression=teams, num_scenarios=64, seed=123)

        driver = {"team": "McLaren", "tyre_compound": "medium", "tyre_age": 24, "current_lap": 24}
        race = {"current_lap": 24, "total_laps": 52, "track_status": "GREEN", "weather": "dry"}

        plan1 = opt1.optimize_driver(driver, race, 21.0, _calc_deg)
        plan2 = opt2.optimize_driver(driver, race, 21.0, _calc_deg)

        assert plan1 == plan2

    def test_agressividade_diferencia_janela_sob_incerteza(self, teams: dict[str, float]) -> None:
        """Equipe agressiva (0.9) para antes da conservadora (0.1) sob incerteza."""
        opt_agg = MonteCarloStrategyOptimizer(team_aggression=teams, num_scenarios=64, seed=99)
        opt_cons = MonteCarloStrategyOptimizer(team_aggression=teams, num_scenarios=64, seed=99)

        pit_agg = None
        pit_cons = None
        for lap in range(1, 45):
            race = {"current_lap": lap, "total_laps": 50, "track_status": "GREEN", "weather": "dry"}
            if pit_agg is None:
                dec = opt_agg.evaluate_driver(
                    {
                        "team": "Red Bull",
                        "tyre_compound": "medium",
                        "tyre_age": lap,
                        "current_lap": lap,
                    },
                    race,
                    21.0,
                    _calc_deg,
                )
                if dec.should_pit:
                    pit_agg = lap
            if pit_cons is None:
                dec = opt_cons.evaluate_driver(
                    {
                        "team": "Kick Sauber",
                        "tyre_compound": "medium",
                        "tyre_age": lap,
                        "current_lap": lap,
                    },
                    race,
                    21.0,
                    _calc_deg,
                )
                if dec.should_pit:
                    pit_cons = lap

        assert pit_agg is not None and pit_cons is not None
        assert pit_agg < pit_cons
        assert (pit_cons - pit_agg) >= 2

    def test_suporta_dataclasses_driver_e_race_state(
        self, optimizer: MonteCarloStrategyOptimizer
    ) -> None:
        """Funciona diretamente com DriverState e RaceState do motor sim/state.py."""
        driver = DriverState(
            driver_id="VER",
            name="Max Verstappen",
            team="Red Bull",
            position=1,
            lap_distance_covered=0.0,
            total_distance_covered=0.0,
            current_lap=28,
            last_lap_time=73.0,
            gap_to_leader=0.0,
            gap_to_ahead=None,
            tyre_compound=TyreCompound.MEDIUM,
            tyre_age=28,
            fuel_load=50.0,
            pit_status=PitStatus.NONE,
            pit_stops_made=0,
            is_retired=False,
            base_velocity=60.0,
        )
        race = RaceState(
            current_lap=28,
            total_laps=55,
            track_status=TrackStatus.GREEN,
            drivers={"VER": driver},
            elapsed_time=2000.0,
        )

        decision = optimizer.evaluate_driver(driver, race, 21.0, _calc_deg)
        assert decision.should_pit is True
        assert decision.target_compound == "hard"
        assert decision.reason == "DEGRADATION"

    def test_validacao_hiperparametros(self) -> None:
        """Rejeita parâmetros inválidos na inicialização."""
        with pytest.raises(ValueError):
            MonteCarloStrategyOptimizer(num_scenarios=0)
        with pytest.raises(ValueError):
            MonteCarloStrategyOptimizer(horizon_laps=0)
        with pytest.raises(ValueError):
            MonteCarloStrategyOptimizer(sc_prob_per_lap=1.5)
        with pytest.raises(ValueError):
            MonteCarloStrategyOptimizer(deg_noise_std=-0.1)


# ===========================================================================
# 3. Camadas Reativas (Bandeira Vermelha, Clima, Safety Car, Undercut)
# ===========================================================================


class TestMonteCarloReactiveLayers:
    def test_bandeira_vermelha_parada_gratuita(
        self, optimizer: MonteCarloStrategyOptimizer
    ) -> None:
        driver = {"team": "Ferrari", "tyre_compound": "medium", "tyre_age": 12, "current_lap": 15}
        race = {"current_lap": 15, "total_laps": 50, "track_status": "RED", "weather": "dry"}
        decision = optimizer.evaluate_driver(driver, race, 21.0, _calc_deg)
        assert decision.should_pit is True
        assert decision.reason == "RED_FLAG"

    def test_crossover_climatico_chuva_e_seco(self, optimizer: MonteCarloStrategyOptimizer) -> None:
        driver_slick = {"team": "McLaren", "tyre_compound": "medium", "tyre_age": 4}
        race_wet = {"current_lap": 10, "total_laps": 50, "track_status": "GREEN", "weather": "wet"}
        dec_wet = optimizer.evaluate_driver(driver_slick, race_wet, 21.0, _calc_deg)
        assert dec_wet.should_pit is True
        assert dec_wet.target_compound == "wet"
        assert dec_wet.reason == "WEATHER"

        driver_wet = {"team": "Aston Martin", "tyre_compound": "wet", "tyre_age": 6}
        race_dry = {"current_lap": 15, "total_laps": 50, "track_status": "GREEN", "weather": "dry"}
        dec_dry = optimizer.evaluate_driver(driver_wet, race_dry, 21.0, _calc_deg)
        assert dec_dry.should_pit is True
        assert dec_dry.target_compound in ("soft", "medium", "hard")
        assert dec_dry.reason == "WEATHER"

    def test_crossover_climatico_umido_e_intermediario(
        self, optimizer: MonteCarloStrategyOptimizer
    ) -> None:
        """Pista úmida (DAMP/umido) troca slick para intermediate e alinha com M4 clima."""
        driver_slick = {"team": "Ferrari", "tyre_compound": "medium", "tyre_age": 8}
        race_damp = {
            "current_lap": 12,
            "total_laps": 50,
            "track_status": "GREEN",
            "weather": "umido",
        }
        dec_damp = optimizer.evaluate_driver(driver_slick, race_damp, 21.0, _calc_deg)
        assert dec_damp.should_pit is True
        assert dec_damp.target_compound == "intermediate"
        assert dec_damp.reason == "WEATHER"

        # Intermediate em pista molhada com poucas voltas restantes (<=5) não força troca
        driver_inter = {"team": "Ferrari", "tyre_compound": "inter", "tyre_age": 6}
        race_wet_late = {
            "current_lap": 46,
            "total_laps": 50,
            "track_status": "GREEN",
            "weather": "molhado",
        }
        dec_late = optimizer.evaluate_driver(driver_inter, race_wet_late, 21.0, _calc_deg)
        assert dec_late.should_pit is False

        # Intermediate em pista molhada com muitas voltas (>5) troca para wet
        race_wet_early = {
            "current_lap": 20,
            "total_laps": 50,
            "track_status": "GREEN",
            "weather": "molhado",
        }
        dec_early = optimizer.evaluate_driver(driver_inter, race_wet_early, 21.0, _calc_deg)
        assert dec_early.should_pit is True
        assert dec_early.target_compound == "wet"
        assert dec_early.reason == "WEATHER"

    def test_clima_dinamico_markov_evita_parada_dupla_antes_da_chuva(
        self, teams: dict[str, float]
    ) -> None:
        """Com alta chance de chuva iminente, Monte Carlo adia parada slick para evitar 2x pit."""
        rain_imminent = {
            "seco": {"seco": 0.45, "umido": 0.45, "molhado": 0.10},
            "umido": {"seco": 0.05, "umido": 0.80, "molhado": 0.15},
            "molhado": {"seco": 0.01, "umido": 0.09, "molhado": 0.90},
        }
        mc_static = MonteCarloStrategyOptimizer(
            team_aggression=teams, num_scenarios=64, seed=42, dynamic_weather=False
        )
        mc_dynamic = MonteCarloStrategyOptimizer(
            team_aggression=teams,
            num_scenarios=64,
            seed=42,
            dynamic_weather=True,
            weather_transition_probs=rain_imminent,
        )

        # Na volta 26 com Red Bull (agressiva), no seco estático já pararia por degradação
        driver = {"team": "Red Bull", "tyre_compound": "medium", "tyre_age": 26, "current_lap": 26}
        race = {"current_lap": 26, "total_laps": 50, "track_status": "GREEN", "weather": "DRY"}

        dec_static = mc_static.evaluate_driver(driver, race, 21.0, _calc_deg)
        dec_dynamic = mc_dynamic.evaluate_driver(driver, race, 21.0, _calc_deg)

        assert dec_static.should_pit is True
        assert dec_dynamic.should_pit is False

    def test_integracao_com_race_engine_m3_e_clima_dinamico_m4(
        self, teams: dict[str, float]
    ) -> None:
        """MonteCarloStrategyOptimizer substitui PitStrategyHeuristic no RaceEngine sem erros."""
        driver = DriverState(
            driver_id="VER",
            name="Max Verstappen",
            team="Red Bull",
            position=1,
            lap_distance_covered=0.0,
            total_distance_covered=0.0,
            current_lap=0,
            last_lap_time=None,
            gap_to_leader=0.0,
            gap_to_ahead=None,
            tyre_compound=TyreCompound.MEDIUM,
            tyre_age=0,
            fuel_load=100.0,
            pit_status=PitStatus.NONE,
            pit_stops_made=0,
            is_retired=False,
            base_velocity=60.0,
        )
        race_state = RaceState(
            current_lap=0,
            total_laps=5,
            track_status=TrackStatus.GREEN,
            drivers={"VER": driver},
            elapsed_time=0.0,
        )
        engine = RaceEngine(
            race_state=race_state,
            track_map=TrackMap.load("interlagos"),
            seed=42,
            weather="DRY",
            dynamic_weather=True,
        )
        engine.pit_heuristic = MonteCarloStrategyOptimizer(
            team_aggression=teams, num_scenarios=32, seed=42, dynamic_weather=True
        )

        for _ in range(3):
            engine.step_lap()

        assert engine.state.current_lap >= 3

    def test_safety_car_antecipa_e_amarela_nao_dispara(
        self, optimizer: MonteCarloStrategyOptimizer
    ) -> None:
        driver = {"team": "Ferrari", "tyre_compound": "medium", "tyre_age": 15, "current_lap": 20}
        race_yellow = {
            "current_lap": 20,
            "total_laps": 50,
            "track_status": "YELLOW",
            "weather": "dry",
        }
        dec_yellow = optimizer.evaluate_driver(driver, race_yellow, 21.0, _calc_deg)
        assert dec_yellow.reason != "SAFETY_CAR"
        assert dec_yellow.should_pit is False

        race_sc = {
            "current_lap": 20,
            "total_laps": 50,
            "track_status": "SAFETY_CAR",
            "weather": "dry",
        }
        dec_sc = optimizer.evaluate_driver(driver, race_sc, 21.0, _calc_deg)
        assert dec_sc.should_pit is True
        assert dec_sc.reason == "SAFETY_CAR"

    def test_undercut_defensivo(self, optimizer: MonteCarloStrategyOptimizer) -> None:
        driver = {
            "team": "Mercedes",
            "tyre_compound": "medium",
            "tyre_age": 12,
            "current_lap": 18,
            "gap_to_car_behind": 1.2,
            "rival_behind_pitted": True,
        }
        race = {"current_lap": 18, "total_laps": 50, "track_status": "GREEN", "weather": "dry"}
        decision = optimizer.evaluate_driver(driver, race, 21.0, _calc_deg)
        assert decision.should_pit is True
        assert decision.reason == "UNDERCUT"


# ===========================================================================
# 4. Benchmark Completo de Desempenho (< 30 segundos)
# ===========================================================================


class TestMonteCarloPerformanceBenchmark:
    def test_simulacao_completa_20_carros_abaixo_de_30_segundos(
        self, teams: dict[str, float]
    ) -> None:
        """Corrida completa (20 carros x 55 voltas) com K=64 roda muito abaixo de 30s."""
        mc = MonteCarloStrategyOptimizer(team_aggression=teams, num_scenarios=64, seed=42)
        team_names = list(teams.keys())
        drivers = [
            {
                "id": f"D{i + 1}",
                "team": team_names[i % len(team_names)],
                "tyre_compound": "medium",
                "tyre_age": 0,
                "pit_laps": [],
            }
            for i in range(20)
        ]

        start = time.perf_counter()
        for lap in range(1, 56):
            race = {
                "current_lap": lap,
                "total_laps": 55,
                "track_status": "GREEN",
                "weather": "dry",
            }
            for d in drivers:
                d["tyre_age"] += 1
                state = {
                    "team": d["team"],
                    "tyre_compound": d["tyre_compound"],
                    "tyre_age": d["tyre_age"],
                    "current_lap": lap,
                }
                decision = mc.evaluate_driver(state, race, 21.0, _calc_deg)
                if decision.should_pit:
                    d["pit_laps"].append(lap)
                    d["tyre_compound"] = decision.target_compound
                    d["tyre_age"] = 0
        elapsed_s = time.perf_counter() - start

        # Critério de desempenho M4: < 30s
        assert elapsed_s < 30.0, f"Execução demorou {elapsed_s:.2f}s (limite 30s)"

        # Todos os 20 carros realizam pit stop em janela realista (voltas 20-33)
        for d in drivers:
            assert len(d["pit_laps"]) >= 1, f"Piloto {d['id']} ({d['team']}) não parou!"
            assert 20 <= d["pit_laps"][0] <= 33, (
                f"Janela irrealista para {d['id']}: {d['pit_laps']}"
            )
