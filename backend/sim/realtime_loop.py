"""
Loop de Simulação em Tempo Real — ApexSim
===========================================

Interface compatível para orquestração da corrida em tempo real.
Reexporta `RaceEngine` e provê o utilitário `run_realtime_loop`.
"""

from __future__ import annotations

from .engine import BroadcastCallback, RaceEngine
from .run import montar_grid_inicial
from .state import RaceState
from .track import TrackMap


async def run_realtime_loop(
    race_state: RaceState | None = None,
    track_length: float = 4309.0,
    race_id: str | None = None,
    seed: int = 42,
    weather: str = "DRY",
    track_temp: float = 32.0,
    delta_time: float = 0.5,
    base_tick_delay: float | None = None,
    base_lap_delay: float = 2.0,
    broadcast_fn: BroadcastCallback | None = None,
    track_map: TrackMap | None = None,
) -> RaceEngine:
    """Instancia e executa o motor de corrida em segundo plano ou até o fim."""
    if race_state is None:
        race_state = montar_grid_inicial()

    engine = RaceEngine(
        race_state=race_state,
        track_length=track_length,
        race_id=race_id,
        seed=seed,
        weather=weather,
        track_temp=track_temp,
        delta_time=delta_time,
        base_tick_delay=base_tick_delay,
        base_lap_delay=base_lap_delay,
        broadcast_fn=broadcast_fn,
        track_map=track_map,
    )
    await engine.run()

    if race_state.is_finished:
        engine.stop()
    
    return engine


__all__ = ["RaceEngine", "run_realtime_loop"]

