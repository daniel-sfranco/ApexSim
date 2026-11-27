import pytest

from app.models.track import TrackMap
from sim.physics import (
    TYRE_TABLE,
    dirty_air_grip_factor,
    dirty_air_time_delta,
    drs_lap_time_gain,
    drs_zone_time_gain,
    fuel_time_delta,
    is_drs_eligible,
    tyre_grip,
    tyre_time_loss,
)


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
        # Soft idade 19: medido 0.8861 +/- 0.4567 s (1.96 * 0.2330)
        soft_19 = tyre_time_loss("soft", 19) - tyre_time_loss("soft", 2)
        assert abs(soft_19 - 0.8861) <= 1.96 * 0.2330

        # Medium idade 29: medido 0.9660 +/- 0.4328 s (1.96 * 0.2208)
        medium_29 = tyre_time_loss("medium", 29) - tyre_time_loss("medium", 2)
        assert abs(medium_29 - 0.9660) <= 1.96 * 0.2208

        # Hard idade 41: medido 1.9243 +/- 0.4151 s (1.96 * 0.2118)
        hard_41 = tyre_time_loss("hard", 41) - tyre_time_loss("hard", 2)
        assert abs(hard_41 - 1.9243) <= 1.96 * 0.2118

    def test_new_tyre_has_near_max_grip(self):
        assert tyre_grip("soft", 0) > 0.98

    def test_invalid_age_raises(self):
        with pytest.raises(ValueError):
            tyre_grip("medium", -1)

    def test_invalid_compound_raises(self):
        with pytest.raises(ValueError):
            tyre_grip("ultrasoft", 5)  # type: ignore[arg-type]

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


class TestDirtyAir:
    def test_clean_air_for_leader_or_large_gap(self):
        assert dirty_air_time_delta(None) == 0.0
        assert dirty_air_grip_factor(None) == 1.0
        assert dirty_air_time_delta(3.5) == 0.0
        assert dirty_air_grip_factor(3.5) == 1.0

    def test_dirty_air_grows_rapidly_below_1s_and_near_zero_above_2s(self):
        """Critério 'Pronto quando' (M3): Perto de zero acima de ~2s; cresce rápido abaixo de 1s."""
        pen_2_2s = dirty_air_time_delta(2.2)
        pen_0_8s = dirty_air_time_delta(0.8)
        pen_0_3s = dirty_air_time_delta(0.3)

        assert pen_2_2s < 0.02
        assert pen_0_3s > pen_0_8s > 0.10
        assert 0.20 <= pen_0_3s <= 0.45
        assert dirty_air_grip_factor(0.3) < dirty_air_grip_factor(1.5) < 1.0

    def test_negative_gap_raises(self):
        with pytest.raises(ValueError):
            dirty_air_time_delta(-0.1)


class TestDRS:
    def test_drs_eligibility_rules(self):
        assert is_drs_eligible(0.7, current_lap=5, track_status="GREEN", is_wet=False) is True
        # Gap >= 1.0s não ativa
        assert is_drs_eligible(1.0, current_lap=5) is False
        assert is_drs_eligible(1.4, current_lap=5) is False
        # Líder (gap None) não ativa
        assert is_drs_eligible(None, current_lap=5) is False
        # Volta 1, pista molhada, SC ou volta imediata de relargada não ativam
        assert is_drs_eligible(0.5, current_lap=1) is False
        assert is_drs_eligible(0.5, current_lap=5, is_wet=True) is False
        assert is_drs_eligible(0.5, current_lap=5, track_status="SC") is False
        assert is_drs_eligible(0.5, current_lap=5, laps_since_restart=0) is False

    def test_drs_consumes_track_map_zones_and_differentiates_circuits(self):
        """Critério 'Pronto quando' (M3): DRS só ativa nas zonas corretas do circuito
        e com gap < 1s.
        """
        interlagos = TrackMap.load("interlagos")
        monza = TrackMap.load("monza")
        monaco = TrackMap.load("monaco")

        # Fora do alcance (gap >= 1s) -> ganho zero
        assert drs_lap_time_gain(interlagos, 1.2, current_lap=10) == 0.0

        # Dentro da janela (gap = 0.6s) -> Interlagos e Monza têm ganho muito superior a Mônaco
        gain_interlagos = drs_lap_time_gain(interlagos, 0.6, current_lap=10)
        gain_monza = drs_lap_time_gain(monza, 0.6, current_lap=10)
        gain_monaco = drs_lap_time_gain(monaco, 0.6, current_lap=10)

        assert gain_interlagos > 0.40
        assert gain_monza > 0.40
        assert 0.0 < gain_monaco < 0.10
        assert gain_interlagos > gain_monaco
        assert drs_zone_time_gain(900.0, eligible=True) == pytest.approx(0.405)
