"""Perfis determinísticos de estratégia por piloto.

O motor aplica estes perfis para que dois pilotos com o mesmo carro não tomem
decisões idênticas de pit stop. Cada piloto recebe um pequeno desvio de:

- ritmo (``pace_offset_ms``), que cria gaps reais ao longo da corrida;
- gestão de pneu (``tyre_factor``), que desloca o limiar de degradação;
- qualidade do pit crew (``pit_crew_delta_s``);
- agressividade (``aggression_jitter``), somada à base da equipe.

Tudo é derivado de ``(seed, driver_id)`` com CRC32, então a corrida continua
100% reproduzível: a mesma seed produz exatamente os mesmos perfis.
"""

from __future__ import annotations

import zlib
from collections.abc import Iterable
from dataclasses import dataclass

from strategy.config import (
    AGGRESSION_JITTER,
    PACE_SPREAD_MS,
    PIT_CREW_SPREAD_S,
    TYRE_MANAGEMENT_SPREAD,
)

# Resolução do hash usado para gerar os desvios determinísticos.
_HASH_RESOLUTION = 100_000


@dataclass(frozen=True)
class DriverProfile:
    """Desvios individuais aplicados ao piloto durante a corrida."""

    driver_id: str
    pace_offset_ms: float
    tyre_factor: float
    pit_crew_delta_s: float
    aggression_jitter: float


def _unit(seed: int, driver_id: str, salt: str) -> float:
    """Retorna um valor determinístico em ``[0, 1)`` para ``(seed, piloto, eixo)``."""
    raw = zlib.crc32(f"{seed}:{driver_id}:{salt}".encode())
    return (raw % _HASH_RESOLUTION) / _HASH_RESOLUTION


def _symmetric(seed: int, driver_id: str, salt: str, spread: float) -> float:
    """Valor determinístico no intervalo ``[-spread, +spread]``."""
    return spread * (2.0 * _unit(seed, driver_id, salt) - 1.0)


def build_driver_profile(seed: int, driver_id: str) -> DriverProfile:
    """Monta o perfil de um piloto a partir da seed da corrida."""
    return DriverProfile(
        driver_id=driver_id,
        pace_offset_ms=_symmetric(seed, driver_id, "pace", PACE_SPREAD_MS),
        tyre_factor=1.0 + _symmetric(seed, driver_id, "tyre", TYRE_MANAGEMENT_SPREAD),
        pit_crew_delta_s=_symmetric(seed, driver_id, "crew", PIT_CREW_SPREAD_S),
        aggression_jitter=_symmetric(seed, driver_id, "aggression", AGGRESSION_JITTER),
    )


def build_driver_profiles(seed: int, driver_ids: Iterable[str]) -> dict[str, DriverProfile]:
    """Monta os perfis de todos os pilotos do grid, indexados por ``driver_id``."""
    return {driver_id: build_driver_profile(seed, driver_id) for driver_id in driver_ids}
