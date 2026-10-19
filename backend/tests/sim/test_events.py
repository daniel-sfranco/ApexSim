import random

import pytest

from app.models.track import TrackMap
from sim.events import (
    SC_COMPRESSED_GAP_AHEAD_S,
    SC_LAP_TIME_MULTIPLIER,
    VSC_LAP_TIME_MULTIPLIER,
    SafetyCarStateMachine,
    build_track_risk_profile,
    incident_consequence_probabilities,
    sample_driver_lap_incident,
)


@pytest.fixture(scope="module")
def interlagos() -> TrackMap:
    return TrackMap.load("interlagos")


@pytest.fixture(scope="module")
def monza() -> TrackMap:
    return TrackMap.load("monza")


@pytest.fixture(scope="module")
def monaco() -> TrackMap:
    return TrackMap.load("monaco")


class TestAccidentGeneratorNHPP:
    def test_risk_profile_covers_full_circuit_length(self, interlagos: TrackMap):
        segments = build_track_risk_profile(interlagos)
        total_len = sum(s.length_m for s in segments)
        assert total_len == pytest.approx(interlagos.length_m)
        assert any(s.is_braking_zone for s in segments)
        assert any(not s.is_braking_zone for s in segments)

    def test_accidents_concentrate_in_braking_zones_over_100_races(self, interlagos: TrackMap):
        """Critério 'Pronto quando' (M3): Em 100 corridas simuladas, os acidentes se
        concentram nas zonas de frenagem (mesmo elas ocupando ~11% do comprimento da pista).
        """
        rng = random.Random(42)
        incidents = []
        for _race in range(100):
            for lap in range(1, 61):
                for driver_idx in range(20):
                    inc = sample_driver_lap_incident(
                        f"D{driver_idx:02d}",
                        lap,
                        interlagos,
                        rng,
                        grip_factor=0.85,
                        weather="seco",
                        aggression=0.5,
                    )
                    if inc is not None:
                        incidents.append(inc)

        assert len(incidents) >= 50
        braking_fraction = sum(1 for i in incidents if i.is_braking_zone) / len(incidents)
        assert braking_fraction > 0.55

    def test_runoff_type_modulates_safety_car_probability(self):
        """Brita e muro devem ter probabilidade de Safety Car substancialmente maior que asfalto."""
        p_sc_asfalto, _, _ = incident_consequence_probabilities("asfalto", "alta")
        p_sc_brita, _, _ = incident_consequence_probabilities("brita", "alta")
        p_sc_muro, _, _ = incident_consequence_probabilities("muro", "alta")
        assert p_sc_asfalto < p_sc_brita < p_sc_muro
        assert p_sc_brita > 0.50
        assert p_sc_asfalto < 0.25

    def test_safety_car_frequency_matches_real_f1_order_of_magnitude(self, interlagos: TrackMap):
        """Critério 'Pronto quando' (M3): Em 100 corridas simuladas (20 carros x 58 voltas),
        a frequência média de Safety Car fica na mesma ordem da estatística real (~1,0 SC/corrida,
        docs/fisica.md Seção 5.4 [25]).
        """
        rng = random.Random(2024)
        total_sc_deployments = 0

        for _race in range(100):
            sm = SafetyCarStateMachine()
            for lap in range(1, 59):
                lap_incidents = []
                # Durante SC/VSC o ritmo é reduzido e não sorteamos novos acidentes de corrida
                if sm.state == "GREEN":
                    for d_idx in range(20):
                        inc = sample_driver_lap_incident(
                            f"D{d_idx:02d}",
                            lap,
                            interlagos,
                            rng,
                            grip_factor=0.88,
                            weather="seco",
                            aggression=0.5,
                        )
                        if inc is not None:
                            lap_incidents.append(inc)
                sm.trigger_from_incidents(lap_incidents, rng)
                sm.advance_lap()
            total_sc_deployments += sm.sc_deployments

        mean_sc_per_race = total_sc_deployments / 100.0
        assert 0.4 <= mean_sc_per_race <= 1.8

    def test_wet_weather_and_low_grip_increase_incident_rate(self, monza: TrackMap):
        rng_dry = random.Random(99)
        rng_wet = random.Random(99)
        n_dry = sum(
            1
            for lap in range(1, 501)
            if sample_driver_lap_incident(
                "VER", lap, monza, rng_dry, grip_factor=0.95, weather="seco"
            )
            is not None
        )
        n_wet = sum(
            1
            for lap in range(1, 501)
            if sample_driver_lap_incident(
                "VER", lap, monza, rng_wet, grip_factor=0.65, weather="molhado"
            )
            is not None
        )
        assert n_wet > n_dry


class TestSafetyCarStateMachine:
    def test_sc_lifecycle_and_drs_restart_lockout(self, interlagos: TrackMap):
        rng = random.Random(7)
        sm = SafetyCarStateMachine()
        assert sm.state == "GREEN"
        assert sm.pace_multiplier == 1.0

        # Simula um incidente que exige SC
        sc_inc = sample_driver_lap_incident("HAM", 10, interlagos, rng, base_intensity_per_m=1.0)
        assert sc_inc is not None
        # Força um incidente com consequência SC
        from dataclasses import replace

        sc_inc = replace(sc_inc, consequence="SC")
        sm.trigger_from_incidents([sc_inc], rng)

        assert sm.state == "SC"
        assert sm.sc_deployments == 1
        assert sm.pace_multiplier == SC_LAP_TIME_MULTIPLIER
        assert 2 <= sm.laps_remaining <= 4

        # Avança voltas até encerrar o SC
        while sm.state == "SC":
            sm.advance_lap()

        assert sm.state == "GREEN"
        # Na volta imediata de relargada após SC, laps_since_restart == 0 (bloqueia DRS)
        assert sm.laps_since_restart == 0
        sm.advance_lap()
        assert sm.laps_since_restart == 1

    def test_vsc_can_escalate_to_sc(self, interlagos: TrackMap):
        from dataclasses import replace

        rng = random.Random(12)
        base_inc = sample_driver_lap_incident("LEC", 5, interlagos, rng, base_intensity_per_m=1.0)
        assert base_inc is not None
        vsc_inc = replace(base_inc, consequence="VSC")
        sc_inc = replace(base_inc, consequence="SC")

        sm = SafetyCarStateMachine()
        sm.trigger_from_incidents([vsc_inc], rng)
        assert sm.state == "VSC"
        assert sm.pace_multiplier == VSC_LAP_TIME_MULTIPLIER

        sm.trigger_from_incidents([sc_inc], rng)
        assert sm.state == "SC"
        assert sm.sc_deployments == 1
        assert sm.vsc_deployments == 1

    def test_compress_gaps_pack_queue(self):
        gaps = SafetyCarStateMachine.compress_gaps([1, 2, 3, 4])
        assert gaps[0] == (0.0, None)
        assert gaps[1] == (SC_COMPRESSED_GAP_AHEAD_S, SC_COMPRESSED_GAP_AHEAD_S)
        assert gaps[3] == (3 * SC_COMPRESSED_GAP_AHEAD_S, SC_COMPRESSED_GAP_AHEAD_S)
