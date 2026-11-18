"""Módulo do Motor de Simulação (ApexSim Core)."""

from .engine import RaceEngine
from .overtaking import OvertakeResult, sample_overtake
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
from .track import TrackMap, Zone

__all__ = [
    "RaceEngine",
    "OvertakeResult",
    "sample_overtake",
    "run_realtime_loop",
    "DriverState",
    "LapResult",
    "PitStatus",
    "RaceState",
    "TrackStatus",
    "TyreCompound",
    "format_lap_update",
    "tick",
    "TrackMap",
    "Zone",
]
