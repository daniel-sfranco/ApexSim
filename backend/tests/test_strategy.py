"""Testes unitários completos para o módulo de estratégia de pit stop (heuristic.py).

Cobre os critérios de aceite:
1. Todas as equipes param em 50 voltas.
2. Distribuição das paradas em janela plausível.
3. Reação a Safety Car (onda de paradas).
4. Variabilidade por Agressividade.
5. Camadas reativas (Bandeira Vermelha, Clima, Undercut).
6. Regra de seleção de composto (Passo 4).
"""

import pytest

from sim.physics import tyre_time_loss
from strategy.heuristic import PitDecision, PitStrategyHeuristic


@pytest.fixture
def heuristic():
    teams = {
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
    return PitStrategyHeuristic(team_aggression=teams)


def _calc_deg(compound: str, age: int) -> float:
    return tyre_time_loss(compound, age, 35.0)


# ===========================================================================
# 1. Testes do Algoritmo Base de Degradação (Passo 2)
# ===========================================================================


class TestBaseDegradationModel:
    def test_pneu_novo_nao_deve_parar(self, heuristic):
        """Um piloto com pneu novo não deve receber ordem de parada."""
        driver = {
            "team": "Ferrari",
            "tyre_compound": "medium",
            "tyre_age": 1,
            "current_lap": 2,
        }
        race = {"current_lap": 2, "total_laps": 50, "track_status": "GREEN", "weather": "dry"}
        decision = heuristic.evaluate_driver(
            driver_state=driver,
            race_state=race,
            pit_lane_loss_s=21.0,
            degradation_curve=_calc_deg,
        )
        assert isinstance(decision, PitDecision)
        assert decision.should_pit is False
        assert decision.reason == "STAY_OUT"

    def test_pneu_muito_velho_deve_parar(self, heuristic):
        """Um piloto com pneu muito degradado (idade 35+) deve acionar parada por degradação."""
        driver = {
            "team": "Ferrari",
            "tyre_compound": "medium",
            "tyre_age": 35,
            "current_lap": 35,
        }
        race = {"current_lap": 35, "total_laps": 50, "track_status": "GREEN", "weather": "dry"}
        decision = heuristic.evaluate_driver(
            driver_state=driver,
            race_state=race,
            pit_lane_loss_s=21.0,
            degradation_curve=_calc_deg,
        )
        assert decision.should_pit is True
        assert decision.reason == "DEGRADATION"
        assert decision.target_compound in ("soft", "medium", "hard")

    def test_variabilidade_por_agressividade(self, heuristic):
        """Equipes com 0.9 e 0.1 tomam decisões em voltas distintas para o mesmo pneu."""
        pit_loss = 21.0
        pit_lap_aggressive = None
        pit_lap_conservative = None

        for lap in range(1, 45):
            r_state = {
                "current_lap": lap,
                "total_laps": 50,
                "track_status": "GREEN",
                "weather": "dry",
            }

            if pit_lap_aggressive is None:
                d_agg = {
                    "team": "Red Bull",
                    "tyre_compound": "medium",
                    "tyre_age": lap,
                    "current_lap": lap,
                }
                dec_agg = heuristic.evaluate_driver(d_agg, r_state, pit_loss, _calc_deg)
                if dec_agg.should_pit:
                    pit_lap_aggressive = lap

            if pit_lap_conservative is None:
                d_cons = {
                    "team": "Kick Sauber",
                    "tyre_compound": "medium",
                    "tyre_age": lap,
                    "current_lap": lap,
                }
                dec_cons = heuristic.evaluate_driver(d_cons, r_state, pit_loss, _calc_deg)
                if dec_cons.should_pit:
                    pit_lap_conservative = lap

        assert pit_lap_aggressive is not None
        assert pit_lap_conservative is not None
        assert pit_lap_aggressive < pit_lap_conservative
        assert (pit_lap_conservative - pit_lap_aggressive) >= 2


# ===========================================================================
# 2. Testes das Camadas Reativas (Passo 3)
# ===========================================================================


class TestReactiveLayers:
    def test_bandeira_vermelha_parada_gratuita(self, heuristic):
        """Bandeira vermelha permite troca sem perda de tempo de corrida."""
        driver = {
            "team": "Ferrari",
            "tyre_compound": "medium",
            "tyre_age": 12,
            "current_lap": 15,
        }
        race = {"current_lap": 15, "total_laps": 50, "track_status": "RED", "weather": "dry"}
        decision = heuristic.evaluate_driver(driver, race, 21.0, _calc_deg)
        assert decision.should_pit is True
        assert decision.reason == "RED_FLAG"
        assert decision.target_compound in ("soft", "medium", "hard")

    def test_crossover_climatico_chuva_imediata(self, heuristic):
        """Transição seco -> molhado força troca imediata para composto de chuva."""
        driver = {
            "team": "McLaren",
            "tyre_compound": "medium",
            "tyre_age": 4,  # Pneu quase novo
            "current_lap": 10,
        }
        race = {"current_lap": 10, "total_laps": 50, "track_status": "GREEN", "weather": "wet"}
        decision = heuristic.evaluate_driver(driver, race, 21.0, _calc_deg)
        assert decision.should_pit is True
        assert decision.target_compound == "wet"
        assert decision.reason == "WEATHER"

    def test_crossover_climatico_seco_imediato(self, heuristic):
        """Transição molhado -> seco força troca imediata para pneu slick."""
        driver = {
            "team": "Aston Martin",
            "tyre_compound": "wet",
            "tyre_age": 6,
            "current_lap": 15,
        }
        race = {"current_lap": 15, "total_laps": 50, "track_status": "GREEN", "weather": "dry"}
        decision = heuristic.evaluate_driver(driver, race, 21.0, _calc_deg)
        assert decision.should_pit is True
        assert decision.target_compound in ("soft", "medium", "hard")
        assert decision.reason == "WEATHER"

    def test_safety_car_antecipa_parada(self, heuristic):
        """Safety Car reduz o custo da parada em ~45% e antecipa paradas de pilotos na janela."""
        driver = {
            "team": "Ferrari",
            "tyre_compound": "medium",
            "tyre_age": 15,
            "current_lap": 20,
        }

        # Em bandeira verde na volta 20 com idade 15, Ferrari ainda ficaria na pista
        race_green = {
            "current_lap": 20,
            "total_laps": 50,
            "track_status": "GREEN",
            "weather": "dry",
        }
        dec_green = heuristic.evaluate_driver(driver, race_green, 21.0, _calc_deg)
        assert dec_green.should_pit is False

        # Sob Safety Car na mesma volta, o custo menor dispara a parada
        race_sc = {
            "current_lap": 20,
            "total_laps": 50,
            "track_status": "SAFETY_CAR",
            "weather": "dry",
        }
        dec_sc = heuristic.evaluate_driver(driver, race_sc, 21.0, _calc_deg)
        assert dec_sc.should_pit is True
        assert dec_sc.reason == "SAFETY_CAR"

    def test_bandeira_amarela_nao_dispara_pit_de_safety_car(self, heuristic):
        """Bandeira amarela simples é incidente local: não reduz o custo do pit nem dispara SAFETY_CAR."""
        driver = {
            "team": "Ferrari",
            "tyre_compound": "medium",
            "tyre_age": 15,
            "current_lap": 20,
        }

        # Mesmo piloto/estado que pararia sob Safety Car, mas sob bandeira amarela.
        race_yellow = {
            "current_lap": 20,
            "total_laps": 50,
            "track_status": "YELLOW",
            "weather": "dry",
        }
        dec_yellow = heuristic.evaluate_driver(driver, race_yellow, 21.0, _calc_deg)

        # Amarela não é tratada como Safety Car: o carro segue a regra base (fica na pista).
        assert dec_yellow.reason != "SAFETY_CAR"
        assert dec_yellow.should_pit is False

    def test_undercut_defensivo(self, heuristic):
        """Se o rival atrás parou na volta anterior e está colado, para defensivamente."""
        driver = {
            "team": "Mercedes",
            "tyre_compound": "medium",
            "tyre_age": 12,
            "current_lap": 18,
            "gap_to_car_behind": 1.2,  # Dentro do limiar de 2.5s
            "rival_behind_pitted": True,  # Rival direto acabou de parar
        }
        race = {
            "current_lap": 18,
            "total_laps": 50,
            "track_status": "GREEN",
            "weather": "dry",
        }
        decision = heuristic.evaluate_driver(driver, race, 21.0, _calc_deg)
        assert decision.should_pit is True
        assert decision.reason == "UNDERCUT"


# ===========================================================================
# 3. Testes da Seleção de Compostos (Passo 4)
# ===========================================================================


class TestCompoundSelection:
    def test_nao_repete_composto_no_seco(self, heuristic):
        """Piloto com pneu Médio não deve trocar de Médio para Médio no seco."""
        driver = {
            "team": "Ferrari",
            "tyre_compound": "medium",
            "tyre_age": 35,
            "current_lap": 35,
        }
        race = {"current_lap": 35, "total_laps": 50, "track_status": "GREEN", "weather": "dry"}
        decision = heuristic.evaluate_driver(driver, race, 21.0, _calc_deg)
        assert decision.should_pit is True
        assert decision.target_compound != "medium"
        assert decision.target_compound in ("soft", "hard")

    def test_composto_macio_no_stint_final(self, heuristic):
        """Faltando menos de 15 voltas, pneu macio deve ser priorizado para stint final."""
        driver = {
            "team": "Red Bull",
            "tyre_compound": "hard",
            "tyre_age": 32,
            "current_lap": 38,
        }
        race = {"current_lap": 38, "total_laps": 50, "track_status": "GREEN", "weather": "dry"}
        decision = heuristic.evaluate_driver(driver, race, 21.0, _calc_deg)
        assert decision.should_pit is True
        assert decision.target_compound == "soft"


# ===========================================================================
# 4. Testes de Critérios de Aceite Globais (Grid Completo de 20 Carros)
# ===========================================================================


class TestGridSimulationAcceptanceCriteria:
    def test_todas_as_equipes_param_e_distribuicao_em_janela(self, heuristic):
        """Numa simulação de 50 voltas:

        - Todos os 20 pilotos realizam ao menos 1 pit stop.
        - As paradas ocorrem distribuídas em uma janela plausível (não todos na mesma volta).
        """
        grid_teams = [
            "Red Bull",
            "Ferrari",
            "Mercedes",
            "McLaren",
            "Aston Martin",
            "Alpine",
            "Williams",
            "Haas",
            "Kick Sauber",
            "RB",
        ]
        # 2 carros por equipe = 20 pilotos
        drivers = [
            {
                "id": f"D{i + 1}",
                "team": grid_teams[i % len(grid_teams)],
                "tyre_compound": "medium",
                "tyre_age": 0,
                "pit_laps": [],
            }
            for i in range(20)
        ]

        pit_loss = 21.0  # Interlagos

        for lap in range(1, 51):
            race = {
                "current_lap": lap,
                "total_laps": 50,
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
                decision = heuristic.evaluate_driver(state, race, pit_loss, _calc_deg)
                if decision.should_pit:
                    d["pit_laps"].append(lap)
                    d["tyre_compound"] = decision.target_compound
                    d["tyre_age"] = 0  # Novo pneu montado

        # Critério 1: Todos os 20 pilotos pararam ao menos 1 vez
        for d in drivers:
            assert len(d["pit_laps"]) >= 1, f"Piloto {d['id']} da {d['team']} não parou!"

        # Critério 2: Distribuição das primeiras paradas em janela
        first_pits = [d["pit_laps"][0] for d in drivers]
        min_lap = min(first_pits)
        max_lap = max(first_pits)

        # Não pararam todos juntos na mesma volta
        assert min_lap < max_lap
        # A janela de abertura e fechamento está em faixa realista da F1
        assert 22 <= min_lap <= 26
        assert 28 <= max_lap <= 32

    def test_onda_de_paradas_com_safety_car(self, heuristic):
        """Injeção de Safety Car na volta 20 dispara onda de paradas imediatas."""
        grid_teams = [
            "Red Bull",
            "Ferrari",
            "Mercedes",
            "McLaren",
            "Aston Martin",
            "Alpine",
            "Williams",
            "Haas",
            "Kick Sauber",
            "RB",
        ]
        drivers = [
            {
                "team": grid_teams[i % len(grid_teams)],
                "tyre_compound": "medium",
                "tyre_age": 19,  # Todos com 19 voltas na volta 20
                "current_lap": 20,
            }
            for i in range(20)
        ]

        # Em bandeira verde na volta 20, equipes conservadoras ainda não parariam
        race_green = {
            "current_lap": 20,
            "total_laps": 50,
            "track_status": "GREEN",
            "weather": "dry",
        }
        pits_green = sum(
            1
            for d in drivers
            if heuristic.evaluate_driver(d, race_green, 21.0, _calc_deg).should_pit
        )

        # Injeta Safety Car na volta 20
        race_sc = {
            "current_lap": 20,
            "total_laps": 50,
            "track_status": "SAFETY_CAR",
            "weather": "dry",
        }
        pits_sc = sum(
            1 for d in drivers if heuristic.evaluate_driver(d, race_sc, 21.0, _calc_deg).should_pit
        )

        # Sob SC, praticamente todo o pelotão que está na volta 20 aproveita a oportunidade
        assert pits_sc > pits_green
        assert pits_sc >= 18  # Quase a totalidade do grid aproveita o SC
