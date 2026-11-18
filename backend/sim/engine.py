"""
Motor de Simulação de F1 — Orquestrador do Motor (RaceEngine)
==============================================================

Orquestra o ciclo de vida da simulação em memória no modo passo a passo (Marco M3):
- Avanço contínuo tick a tick (delta_time = 0.5s) com telemetria espacial (distance_m).
- Integração com física de pneus, combustível, ar sujo e DRS (sim.physics).
- Avaliação de estratégias de pit stop em tempo real (strategy.heuristic).
- Despacho contínuo de mensagens `lap_update` e `event_update` (Contrato D2).
- Zero dependência externa ou I/O web (pureza de domínio).
"""

from __future__ import annotations

import asyncio
import inspect
import random
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sim.physics import tyre_time_loss
from sim.state import (
    PitStatus,
    RaceState,
    TyreCompound,
    format_lap_update,
    tick,
    todos_pilotos_finalizados,
)
from sim.track import TrackMap
from strategy.heuristic import PitStrategyHeuristic

BroadcastCallback = Callable[[dict[str, Any]], Awaitable[None] | None]


class RaceEngine:
    """Orquestrador assíncrono do motor de corrida em memória."""

    def __init__(
        self,
        race_state: RaceState,
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
    ) -> None:
        """Inicializa o motor da corrida.

        Args:
            race_state: Estado inicial da corrida (grid montado).
            track_length: Extensão linear do circuito em metros.
            race_id: Identificador único da corrida.
            seed: Semente determinística.
            weather: Condição climática inicial ("DRY", "DAMP", "WET").
            track_temp: Temperatura da pista em Celsius.
            delta_time: Passo de tempo da simulação por tick (default: 0.5s).
            base_tick_delay: Intervalo real de sono por tick a 1x (default: 0.04s = 25 Hz).
            base_lap_delay: Legado para retrocompatibilidade.
            broadcast_fn: Callback assíncrono para envio de envelopes.
            track_map: Mapa semântico de pista 1D (Contrato D4).
        """
        self.state = race_state
        self.track_length = float(track_length)
        self.race_id = race_id or str(uuid.uuid4())
        self.seed = int(seed)
        self.rng = random.Random(self.seed)
        self.weather = weather
        self.track_temp = float(track_temp)
        self.delta_time = float(delta_time)
        self.base_lap_delay = float(base_lap_delay)
        if base_tick_delay is not None:
            self.base_tick_delay = float(base_tick_delay)
        elif self.base_lap_delay < 1.0:
            self.base_tick_delay = 0.0
        else:
            self.base_tick_delay = 0.4
        self.broadcast_fn = broadcast_fn
        self.track_map = track_map

        if self.track_map is not None:
            self.track_length = float(self.track_map.length_m)

        self.is_paused: bool = False
        self.speed_multiplier: float = 1.0
        self.is_stopped: bool = False

        self._pause_event = asyncio.Event()
        self._pause_event.set()

        self.pending_events: list[dict[str, Any]] = []
        self.pit_heuristic = PitStrategyHeuristic()

    # -----------------------------------------------------------------------
    # CONTROLES DE FLUXO EM TEMPO REAL
    # -----------------------------------------------------------------------

    def play(self) -> None:
        """Retoma o avanço da simulação."""
        self.is_paused = False
        self._pause_event.set()

    def resume(self) -> None:
        """Alias para play()."""
        self.play()

    def pause(self) -> None:
        """Pausa o avanço da simulação sem descarregar o estado."""
        self.is_paused = True
        self._pause_event.clear()

    def set_speed(self, multiplier: float) -> None:
        """Ajusta o multiplicador de velocidade da simulação (0.25x a 20.0x)."""
        clamped = max(0.25, min(20.0, float(multiplier)))
        self.speed_multiplier = clamped

    def stop(self) -> None:
        """Encerra a execução do motor."""
        self.is_stopped = True
        self._pause_event.set()

    def handle_command(self, cmd: dict[str, Any]) -> None:
        """Processa comandos de controle enviados pelo cliente WebSocket."""
        action = cmd.get("action")
        if action in ("play", "resume"):
            self.play()
        elif action == "pause":
            self.pause()
        elif action == "set_speed":
            multiplier = cmd.get("speed_multiplier", 1.0)
            self.set_speed(multiplier)
        elif action == "stop":
            self.stop()

    # -----------------------------------------------------------------------
    # TELEMETRIA E ENVELOPES D2
    # -----------------------------------------------------------------------

    def get_lap_update_envelope(self) -> dict[str, Any]:
        """Gera o envelope formal `lap_update` segundo o Contrato D2."""
        return format_lap_update(
            state=self.state,
            race_id=self.race_id,
            weather=self.weather,
            track_temp=self.track_temp,
        )

    # -----------------------------------------------------------------------
    # AVANÇO DE SIMULAÇÃO PASSO A PASSO
    # -----------------------------------------------------------------------

    def step_tick(self, delta_time: float | None = None) -> None:
        """Avança a simulação em exatamente um passo de tempo (tick)."""
        if self.state.is_finished:
            return

        dt = float(delta_time if delta_time is not None else self.delta_time)

        # Avaliação de pit stops via heurística de estratégia antes do movimento
        for driver in self.state.drivers.values():
            if driver.is_retired or driver.pit_status != PitStatus.NONE:
                continue

            # Avalia se deve parar quando estiver na aproximação final da volta
            # (últimos 15% do traçado ou início de volta)
            na_janela_de_pit = (
                driver.lap_distance_covered > 0.85 * self.track_length
                or driver.lap_distance_covered < 0.05 * self.track_length
            )

            if na_janela_de_pit and driver.current_lap >= 2:
                decision = self.pit_heuristic.evaluate_driver(
                    driver_state=driver,
                    race_state=self.state,
                    pit_lane_loss_s=22.0,
                    degradation_curve=lambda c, a: tyre_time_loss(c, a, self.track_temp),
                )
                if decision.should_pit:
                    target_name = (decision.target_compound or "medium").upper()
                    try:
                        novo_composto = TyreCompound[target_name]
                    except KeyError:
                        novo_composto = TyreCompound.MEDIUM

                    driver.pit_status = PitStatus.IN_PIT
                    driver.pit_time_remaining = 22.0
                    driver.pit_stops_made += 1
                    driver.pit_stop_in_this_lap = True
                    driver.pit_time_in_this_lap = 22.0
                    driver.tyre_compound = novo_composto
                    driver.tyre_age = 0

                    self.pending_events.append(
                        {
                            "type": "event_update",
                            "race_id": self.race_id,
                            "lap": driver.current_lap,
                            "event_type": "PIT_STOP",
                            "involved_drivers": [driver.driver_id],
                            "zone_id": "pit_lane",
                            "description": (
                                f"{driver.name} ({driver.team}) realizou pit stop "
                                f"e colocou pneus {target_name} ({decision.reason})."
                            ),
                        }
                    )

        # Avança a física e deslocamento em 1 tick
        tick(
            state=self.state,
            delta_time=dt,
            track_length=self.track_length,
            rng=self.rng,
            track_map=self.track_map,
            track_temp=self.track_temp,
            use_physics=True,
        )

        if todos_pilotos_finalizados(self.state):
            self.state.is_finished = True

    def step_lap(self) -> None:
        """Avança ticks até que a próxima volta seja concluída pelo líder (lote)."""
        if self.state.is_finished:
            return

        starting_lap = self.state.current_lap
        target_lap = starting_lap + 1
        ticks_count = 0
        max_ticks = 2000

        while ticks_count < max_ticks and not self.state.is_finished:
            self.step_tick(self.delta_time)
            ticks_count += 1
            if self.state.current_lap >= target_lap and target_lap < self.state.total_laps:
                break

    async def _emit_broadcast(self, envelope: dict[str, Any]) -> None:
        """Emite o envelope para o callback de broadcast se configurado."""
        if self.broadcast_fn is None:
            return

        if inspect.iscoroutinefunction(self.broadcast_fn):
            await self.broadcast_fn(envelope)
        else:
            res = self.broadcast_fn(envelope)
            if inspect.isawaitable(res):
                await res

    # -----------------------------------------------------------------------
    # LOOP PRINCIPAL ASSÍNCRONO PASSO A PASSO
    # -----------------------------------------------------------------------

    async def run(self) -> None:
        """Executa o loop contínuo da corrida passo a passo em tempo real."""
        # Emite snapshot inicial da volta de formação/grid
        if self.state.current_lap == 0 and self.state.elapsed_time == 0.0:
            await self._emit_broadcast(self.get_lap_update_envelope())

        while not self.state.is_finished and not self.is_stopped:
            if self.is_paused:
                await self._pause_event.wait()

            if self.is_stopped:
                break

            self.step_tick(self.delta_time)
            await self._emit_broadcast(self.get_lap_update_envelope())

            # Emite eventos pendentes gerados neste tick (ex: pit stops)
            while self.pending_events:
                event = self.pending_events.pop(0)
                await self._emit_broadcast(event)

            # Pausa ajustada pela velocidade configurada
            sleep_duration = (
                self.base_tick_delay / self.speed_multiplier
                if self.speed_multiplier > 0
                else self.base_tick_delay
            )
            if sleep_duration > 0.001:
                await asyncio.sleep(sleep_duration)
            else:
                await asyncio.sleep(0)
