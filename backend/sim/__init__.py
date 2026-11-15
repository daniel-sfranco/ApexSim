"""Módulo do Motor de Simulação (ApexSim Core)."""

from .engine import RaceEngine
from .events import RaceIncident, SafetyCarStateMachine
from .overtaking import OvertakeResult, sample_overtake
from .physics import fuel_time_delta, tyre_grip, tyre_time_loss
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
from .weather import WeatherSimulator, weather_grip_factor, weather_time_delta

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
    "fuel_time_delta",
    "tyre_grip",
    "tyre_time_loss",
    "RaceIncident",
    "SafetyCarStateMachine",
    "WeatherSimulator",
    "weather_grip_factor",
    "weather_time_delta",
]
