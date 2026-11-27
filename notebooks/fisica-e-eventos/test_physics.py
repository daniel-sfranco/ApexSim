import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from physics import TYRE_TABLE, fuel_time_delta, tyre_grip, tyre_time_loss


class TestTyreGrip:
    def test_grip_decreases_with_age(self):
        g0 = tyre_grip("medium", 0)
        g20 = tyre_grip("medium", 20)
        g39 = tyre_grip("medium", 39)
        assert g0 > g20 > g39

    def test_grip_bounded_between_0_and_1(self):
        for compound in TYRE_TABLE:
            for age in range(0, 51, 5):
                g = tyre_grip(compound, age)
                assert 0.0 < g <= 1.0

    def test_cliff_longevity_and_post_cliff_ordering(self):
        """A vida util ate o cliff (hipotese de modelagem) segue Soft < Medium < Hard,
        e em stints longos (apos o cliff do Medium) a perda segue Soft > Medium > Hard."""
        assert (
            TYRE_TABLE["soft"].cliff_age
            < TYRE_TABLE["medium"].cliff_age
            < TYRE_TABLE["hard"].cliff_age
        )

        # Na faixa medida (ex.: volta 15), o Soft degrada mais que o Medium
        assert tyre_time_loss("soft", 15) > tyre_time_loss("medium", 15)

        # Apos o cliff do Medium (ex.: volta 38), a hierarquia teorica completa se estabelece
        age = 38
        loss_soft = tyre_time_loss("soft", age)
        loss_medium = tyre_time_loss("medium", age)
        loss_hard = tyre_time_loss("hard", age)
        assert loss_soft > loss_medium > loss_hard

    def test_matches_measured_ic95_at_max_supported_age(self):
        """Garante que na ultima idade medida de cada composto (relativa a idade de
        referencia 2) o modelo permanece dentro do IC 95% de curvas_degradacao.json."""
        soft_19 = tyre_time_loss("soft", 19) - tyre_time_loss("soft", 2)
        assert abs(soft_19 - 0.8861) <= 1.96 * 0.2330

        medium_29 = tyre_time_loss("medium", 29) - tyre_time_loss("medium", 2)
        assert abs(medium_29 - 0.9660) <= 1.96 * 0.2208

        hard_41 = tyre_time_loss("hard", 41) - tyre_time_loss("hard", 2)
        assert abs(hard_41 - 1.9243) <= 1.96 * 0.2118

    def test_new_tyre_has_near_max_grip(self):
        assert tyre_grip("soft", 0) > 0.98

    def test_invalid_age_raises(self):
        with pytest.raises(ValueError):
            tyre_grip("medium", -1)

    def test_invalid_compound_raises(self):
        with pytest.raises(ValueError):
            tyre_grip("ultrasoft", 5)

    def test_temperature_penalty_outside_window(self):
        cold = tyre_time_loss("medium", 10, track_temp=15.0)
        ideal = tyre_time_loss("medium", 10, track_temp=35.0)
        hot = tyre_time_loss("medium", 10, track_temp=60.0)
        assert cold > ideal
        assert hot > ideal


class TestFuelTimeDelta:
    def test_zero_fuel_zero_penalty(self):
        assert fuel_time_delta(0.0) == 0.0

    def test_monotonic_in_fuel_mass(self):
        assert fuel_time_delta(10) < fuel_time_delta(50) < fuel_time_delta(100)

    def test_order_of_magnitude_per_10kg(self):
        """Carro cheio deve ser mais lento na ordem de ~0.3s por 10kg
        (criterio 'Pronto quando' do M1). A calibracao de referencia
        (McLaren, 0.03 s/kg) da exatamente 0.3s por 10kg."""
        delta_10kg = fuel_time_delta(10) - fuel_time_delta(0)
        assert 0.2 <= delta_10kg <= 0.5

    def test_negative_fuel_raises(self):
        with pytest.raises(ValueError):
            fuel_time_delta(-5)
