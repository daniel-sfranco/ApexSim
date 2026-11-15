import random

import pytest

from sim.weather import (
    DEFAULT_TRANSITION_PROBABILITIES,
    WeatherSimulator,
    weather_grip_factor,
    weather_time_delta,
)


class TestWeatherSimulator:
    def test_initial_state_defaults_to_seco(self):
        sim = WeatherSimulator()
        assert sim.current_state == "seco"
        assert sim.wetness == 0.0

    def test_deterministic_advance_with_seeded_rng(self):
        sim1 = WeatherSimulator(current_state="seco")
        sim2 = WeatherSimulator(current_state="seco")

        rng1 = random.Random(42)
        rng2 = random.Random(42)

        history1 = [sim1.advance_lap(rng1) for _ in range(50)]
        history2 = [sim2.advance_lap(rng2) for _ in range(50)]

        assert history1 == history2
        # Transições devem ser válidas dentro dos estados previstos
        for state in history1:
            assert state in ("seco", "umido", "molhado")

    def test_transition_probability_rows_sum_to_one(self):
        for _state, row in DEFAULT_TRANSITION_PROBABILITIES.items():
            assert pytest.approx(sum(row.values()), rel=1e-5) == 1.0


class TestWeatherCompoundCrossover:
    def test_dry_condition_slicks_are_optimal(self):
        # No seco, slicks não têm penalidade climática
        assert weather_time_delta("soft", "seco") == 0.0
        assert weather_time_delta("medium", "seco") == 0.0
        assert weather_time_delta("hard", "seco") == 0.0

        # Pneu de chuva no seco tem penalidade severa
        assert weather_time_delta("intermediate", "seco") > 3.0
        assert weather_time_delta("wet", "seco") > 7.0

        # Grip é máximo nos slicks
        assert weather_grip_factor("soft", "seco") == 1.0
        assert weather_grip_factor("intermediate", "seco") < 1.0

    def test_damp_condition_intermediate_is_optimal(self):
        # Na pista úmida, Intermediate é o composto de crossover
        inter_loss = weather_time_delta("intermediate", "umido")
        soft_loss = weather_time_delta("soft", "umido")
        wet_loss = weather_time_delta("wet", "umido")

        assert inter_loss < soft_loss
        assert inter_loss < wet_loss

        # Grip do intermediário é superior aos slicks no úmido
        assert weather_grip_factor("intermediate", "umido") > weather_grip_factor("soft", "umido")

    def test_wet_condition_full_wet_is_optimal(self):
        # Na chuva pesada, Full Wet é o melhor
        wet_loss = weather_time_delta("wet", "molhado")
        inter_loss = weather_time_delta("intermediate", "molhado")
        soft_loss = weather_time_delta("soft", "molhado")

        assert wet_loss < inter_loss < soft_loss

        # Slicks sofrem penalidade extrema (aquaplanagem)
        assert soft_loss >= 15.0

    def test_case_insensitivity_and_aliases(self):
        assert weather_time_delta("SOFT", "SECO") == 0.0
        assert weather_time_delta("inter", "umido") == weather_time_delta("intermediate", "umido")

    def test_invalid_compound_raises(self):
        with pytest.raises(ValueError):
            weather_time_delta("hypersoft", "seco")

    def test_invalid_weather_state_raises(self):
        with pytest.raises(ValueError):
            weather_time_delta("soft", "neve")
