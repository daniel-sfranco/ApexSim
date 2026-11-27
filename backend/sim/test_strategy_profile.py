"""Testes dos perfis determinísticos de estratégia por piloto."""

from sim.strategy_profile import build_driver_profile, build_driver_profiles
from strategy.config import (
    AGGRESSION_JITTER,
    PACE_SPREAD_MS,
    PIT_CREW_SPREAD_S,
    TYRE_MANAGEMENT_SPREAD,
)


def test_perfil_e_deterministico_por_seed_e_piloto():
    """A mesma seed e o mesmo piloto produzem exatamente o mesmo perfil."""
    assert build_driver_profile(42, "VER") == build_driver_profile(42, "VER")
    assert build_driver_profile(42, "VER") != build_driver_profile(43, "VER")


def test_perfis_respeitam_os_limites_configurados():
    """Todos os desvios ficam dentro das faixas declaradas em `strategy.config`."""
    perfis = build_driver_profiles(42, ["VER", "NOR", "HAM"])

    assert set(perfis) == {"VER", "NOR", "HAM"}
    for perfil in perfis.values():
        assert abs(perfil.pace_offset_ms) <= PACE_SPREAD_MS
        assert 1.0 - TYRE_MANAGEMENT_SPREAD <= perfil.tyre_factor <= 1.0 + TYRE_MANAGEMENT_SPREAD
        assert abs(perfil.pit_crew_delta_s) <= PIT_CREW_SPREAD_S
        assert abs(perfil.aggression_jitter) <= AGGRESSION_JITTER


def test_pilotos_diferentes_recebem_perfis_diferentes():
    """O grid não compartilha o mesmo desvio de ritmo nem de gestão de pneu."""
    perfis = build_driver_profiles(42, ["VER", "NOR", "HAM", "PER"])

    assert len({perfil.pace_offset_ms for perfil in perfis.values()}) > 1
    assert len({perfil.tyre_factor for perfil in perfis.values()}) > 1
