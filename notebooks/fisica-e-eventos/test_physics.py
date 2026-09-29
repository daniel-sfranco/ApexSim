"""
tests/test_physics.py

Testes unitarios para apexsim/physics.py (funcoes puras).
Rodar com: pytest tests/test_physics.py -v
"""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent))

try:
    from apexsim.physics import tyre_grip, tyre_time_loss, fuel_time_delta, TYRE_TABLE
except ImportError:
    from physics import tyre_grip, tyre_time_loss, fuel_time_delta, TYRE_TABLE


class TestTyreGrip:
    def test_grip_decreases_with_age(self):
        g0 = tyre_grip("medium", 0)
        g20 = tyre_grip("medium", 20)
        g39 = tyre_grip("medium", 39)
        assert g0 > g20 > g39

    def test_grip_bounded_between_0_and_1(self):
        for compound in TYRE_TABLE:
            for age in range(0, 41, 5):
                g = tyre_grip(compound, age)
                assert 0.0 < g <= 1.0

    def test_compound_degradation_ordering(self):
        """Macio degrada mais rapido que medio, que degrada mais rapido
        que duro (criterio 'Pronto quando' do M1)."""
        age = 25
        loss_soft = tyre_time_loss("soft", age)
        loss_medium = tyre_time_loss("medium", age)
        loss_hard = tyre_time_loss("hard", age)
        assert loss_soft > loss_medium > loss_hard

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
