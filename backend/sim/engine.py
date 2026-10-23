"""
Motor de Simulação de F1 — Orquestrador do Motor (RaceEngine)
==============================================================

Este módulo orquestra o ciclo de vida da simulação em memória:
- Gerencia o loop assíncrono em tempo real modulado por velocidade (play, pause, set_speed).
- Assegura determinismo através de injeção de `random.Random(seed)`.
- Dispara callbacks de broadcast a cada volta concluída com o envelope do Contrato D2.
- Respeita o princípio de Bounded Context: zero dependência de FastAPI ou WebSockets.
"""

from __future__ import annotations

import asyncio
import inspect
import random
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from .state import RaceState, format_lap_update, tick

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
        base_lap_delay: float = 2.0,
        broadcast_fn: BroadcastCallback | None = None,
    ) -> None:
        """Inicializa o motor da corrida.

        Args:
            race_state: Estado inicial da corrida (grid montado).
            track_length: Extensão linear do circuito em metros (default: Interlagos, 4309m).
            race_id: Identificador único da corrida (UUID). Gerado automaticamente se omitido.
            seed: Semente determinística para o gerador de números aleatórios.
            weather: Condição meteorológica inicial ("DRY", "WET", etc.).
            track_temp: Temperatura da pista em graus Celsius.
            base_lap_delay: Tempo base em segundos reais de espera entre voltas a 1x.
            broadcast_fn: Callback assíncrono disparado a cada volta concluída com o envelope D2.
        """
        self.state = race_state
        self.track_length = float(track_length)
        self.race_id = race_id or str(uuid.uuid4())
        self.seed = int(seed)
        self.rng = random.Random(self.seed)
        self.weather = weather
        self.track_temp = float(track_temp)
        self.base_lap_delay = float(base_lap_delay)
        self.broadcast_fn = broadcast_fn

        self.is_paused: bool = False
        self.speed_multiplier: float = 1.0
        self.is_stopped: bool = False

        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Inicia despausado por padrão

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
        """Ajusta o multiplicador de velocidade da simulação (ex.: 0.5x, 1x, 2x, 5x, 10x)."""
        clamped = max(0.25, min(20.0, float(multiplier)))
        self.speed_multiplier = clamped

    def stop(self) -> None:
        """Encerra a execução do motor."""
        self.is_stopped = True
        self._pause_event.set()

    def handle_command(self, cmd: dict[str, Any]) -> None:
        """Processa comandos de controle em tempo real enviados pelo cliente.

        Comandos suportados segundo o Contrato D2:
            { "action": "play" } ou { "action": "resume" }
            { "action": "pause" }
            { "action": "set_speed", "speed_multiplier": float }
            { "action": "stop" }
        """
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
    # TELEMETRIA E ENVELOPE D2
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
    # AVANÇO DE SIMULAÇÃO
    # -----------------------------------------------------------------------

    def step_lap(self) -> None:
        """Avança a simulação até que a próxima volta seja concluída pelo líder."""
        if self.state.is_finished:
            return

        starting_lap = self.state.current_lap
        target_lap = starting_lap + 1
        delta_time = 1.0  # Passos de 1 segundo de simulação

        # Continua avançando até que a volta atual da corrida avance
        ticks_count = 0
        max_ticks = 1000  # Trava de segurança para evitar loops infinitos
        while (
            self.state.current_lap < target_lap
            and not self.state.is_finished
            and ticks_count < max_ticks
        ):
            tick(
                state=self.state,
                delta_time=delta_time,
                track_length=self.track_length,
                rng=self.rng,
            )
            ticks_count += 1

        if self.state.current_lap >= self.state.total_laps:
            self.state.is_finished = True

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
    # LOOP PRINCIPAL ASSÍNCRONO
    # -----------------------------------------------------------------------

    async def run(self) -> None:
        """Executa o loop contínuo da corrida em tempo real.

        Emite um snapshot inicial se a corrida estiver na volta 0, avança
        volta a volta respeitando pausas e velocidade, e notifica via
        broadcast_fn até o encerramento da corrida.
        """
        # Emite snapshot inicial da volta de formação/grid
        if self.state.current_lap == 0:
            await self._emit_broadcast(self.get_lap_update_envelope())

        while not self.state.is_finished and not self.is_stopped:
            if self.is_paused:
                await self._pause_event.wait()

            if self.is_stopped:
                break

            self.step_lap()
            await self._emit_broadcast(self.get_lap_update_envelope())

            # Pausa ajustada pela velocidade configurada
            sleep_duration = max(0.01, self.base_lap_delay / self.speed_multiplier)
            await asyncio.sleep(sleep_duration)
