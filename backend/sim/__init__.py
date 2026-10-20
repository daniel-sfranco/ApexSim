"""Módulo do Motor de Simulação (ApexSim Core)."""

from .engine import RaceEngine
from .realtime_loop import run_realtime_loop
from .state import (
    DriverState,
    LapResult,
    PitStatus,
    RaceState,
    TrackStatus,
    TyreCompound,
    format_lap_update,
    tick,
)

__all__ = [
    "RaceEngine",
    "run_realtime_loop",
    "DriverState",
    "LapResult",
    "PitStatus",
    "RaceState",
    "TrackStatus",
    "TyreCompound",
    "format_lap_update",
    "tick",
]

