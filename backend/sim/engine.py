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

from sim.events import RaceIncident, SafetyCarStateMachine, sample_driver_lap_incident
from sim.overtaking import compound_name, sample_overtake
from sim.physics import tyre_grip, tyre_time_loss
from sim.state import (
    DriverState,
    LapResult,
    PitStatus,
    RaceState,
    TrackStatus,
    TyreCompound,
    format_lap_update,
    tick,
    todos_pilotos_finalizados,
)
from sim.track import TrackMap
from strategy.heuristic import PitStrategyHeuristic

BroadcastCallback = Callable[[dict[str, Any]], Awaitable[None] | None]

# Gancho de "fim de volta": recebe as voltas (`LapResult`) fechadas desde a última
# chamada e os envelopes `event_update` emitidos no mesmo intervalo. É por onde a
# camada de aplicação grava a corrida no banco sem que o `sim/` saiba que há banco.
LapClosedCallback = Callable[[list[LapResult], list[dict[str, Any]]], Awaitable[None]]
# Chamado uma única vez, depois do último `on_lap_closed`, quando a corrida termina.
FinishedCallback = Callable[[], Awaitable[None]]

# Mapeia o clima do contrato D2 ("DRY"/"DAMP"/"WET") para o vocabulário do
# gerador de incidentes (sim.events).
WEATHER_TO_INCIDENT_CONDITION: dict[str, str] = {
    "DRY": "seco",
    "SECO": "seco",
    "DAMP": "umido",
    "UMIDO": "umido",
    "WET": "molhado",
    "MOLHADO": "molhado",
}

# Mapeia a máquina de estados de direção de prova para o enum do Contrato D2.
RACE_CONTROL_TO_TRACK_STATUS: dict[str, TrackStatus] = {
    "GREEN": TrackStatus.GREEN,
    "VSC": TrackStatus.YELLOW,
    "SC": TrackStatus.SAFETY_CAR,
}

# Clima no vocabulário da heurística de estratégia (`strategy.heuristic`), que
# distingue apenas pista seca ("dry") de molhada ("wet"); "damp" é neutro.
WEATHER_TO_HEURISTIC_CONDITION: dict[str, str] = {
    "DRY": "dry",
    "SECO": "dry",
    "DAMP": "damp",
    "UMIDO": "damp",
    "WET": "wet",
    "MOLHADO": "wet",
}

# Janela (voltas) em que a parada do rival de trás ainda configura undercut.
UNDERCUT_WINDOW_LAPS = 2

# Compostos de chuva não existem na tabela de degradação seca (`sim.physics`);
# a heurística os projeta usando o slick equivalente (mesma convenção de
# `sim.state.tick()` e `sim.overtaking.compound_name`).
STRATEGY_DEGRADATION_PROXY: dict[str, str] = {
    "intermediate": "medium",
    "wet": "medium",
}


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
        on_lap_closed: LapClosedCallback | None = None,
        on_finished: FinishedCallback | None = None,
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
            on_lap_closed: Gancho chamado uma vez por volta do líder (nunca por
                tick) com as voltas e eventos novos. O loop espera o gancho
                terminar antes de seguir, então o histórico chega em ordem.
            on_finished: Gancho chamado quando a corrida termina normalmente
                (não é chamado se o motor for parado com `stop()`).
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
            self.base_tick_delay = 0.04
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

        # Valores de pit lane vindos do Contrato D4 (com fallback seguro).
        if self.track_map is not None:
            self.pit_lane_loss_s = self.track_map.pit_time_loss_s()
            self.pit_speed_limit_ms = self.track_map.pit_speed_limit_ms()
        else:
            self.pit_lane_loss_s = 22.0
            self.pit_speed_limit_ms = 22.2

        # Direção de prova (Safety Car / VSC) e controle de voltas.
        self.race_control = SafetyCarStateMachine()
        self._previous_race_lap = race_state.current_lap
        self._lap_incidents: list[RaceIncident] = []

        # Volta da última parada de cada piloto (contexto de undercut da heurística).
        self._last_pit_lap: dict[str, int] = {}

        # Ganchos de fim de volta / fim de corrida (persistência, fora do sim/).
        self.on_lap_closed = on_lap_closed
        self.on_finished = on_finished
        # Quantas entradas de `lap_history` já foram entregues ao gancho.
        self._laps_delivered = 0
        # Eventos emitidos desde a última entrega ao gancho. `pending_events` não
        # serve: ele é esvaziado a cada tick pelo broadcast.
        self._events_since_lap_closed: list[dict[str, Any]] = []
        # Marcado pelo `step_tick` quando o líder fecha uma volta.
        self._race_lap_closed = False

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
        try:
            val = float(multiplier)
        except (ValueError, TypeError):
            val = 1.0
        clamped = max(0.25, min(20.0, val))
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

        self._advance_cooldowns(dt)
        self._evaluate_pit_stops()
        self._resolve_overtakes()

        laps_before = {d.driver_id: d.current_lap for d in self.state.drivers.values()}

        # Avança a física e deslocamento em 1 tick
        tick(
            state=self.state,
            delta_time=dt,
            track_length=self.track_length,
            rng=self.rng,
            track_map=self.track_map,
            track_temp=self.track_temp,
            use_physics=True,
            laps_since_restart=self.race_control.laps_since_restart,
            is_wet=not self.is_dry,
            pit_speed_limit_ms=self.pit_speed_limit_ms,
        )

        # Eventos estocásticos e direção de prova (M3)
        incidents = self._sample_lap_incidents(laps_before)
        for incident in incidents:
            self._apply_incident(incident)
            self._lap_incidents.append(incident)

        if self.state.current_lap > self._previous_race_lap:
            self._on_new_race_lap(self._lap_incidents)
            self._lap_incidents = []
            self._previous_race_lap = self.state.current_lap
            self._race_lap_closed = True

        if todos_pilotos_finalizados(self.state):
            self.state.is_finished = True

    # -----------------------------------------------------------------------
    # ESTRATÉGIA, ULTRAPASSAGEM E DIREÇÃO DE PROVA
    # -----------------------------------------------------------------------

    @property
    def is_dry(self) -> bool:
        """True quando a pista está seca (habilita DRS e reduz risco)."""
        return str(self.weather).strip().upper() in ("DRY", "SECO")

    @property
    def incident_weather(self) -> str:
        """Clima no vocabulário do gerador de incidentes (`sim.events`)."""
        return WEATHER_TO_INCIDENT_CONDITION.get(str(self.weather).strip().upper(), "seco")

    @property
    def heuristic_weather(self) -> str:
        """Clima no vocabulário da heurística de estratégia (`strategy.heuristic`)."""
        return WEATHER_TO_HEURISTIC_CONDITION.get(str(self.weather).strip().upper(), "dry")

    def _aggression_for(self, team: str) -> float:
        """Agressividade da equipe configurada na heurística de estratégia."""
        return self.pit_heuristic.team_aggression.get(team, 0.5)

    def _queue_event(
        self,
        event_type: str,
        involved_drivers: list[str],
        description: str,
        *,
        zone_id: str | None = None,
        lap: int | None = None,
    ) -> None:
        """Enfileira um envelope `event_update` (Contrato D2)."""
        envelope = {
            "type": "event_update",
            "race_id": self.race_id,
            "lap": int(lap if lap is not None else self.state.current_lap),
            "event_type": event_type,
            "involved_drivers": list(involved_drivers),
            "zone_id": zone_id,
            "description": description,
        }
        self.pending_events.append(envelope)
        if self.on_lap_closed is not None:
            self._events_since_lap_closed.append(envelope)

    def _advance_cooldowns(self, delta_time: float) -> None:
        """Decrementa o cooldown de ultrapassagem de cada piloto."""
        for driver in self.state.drivers.values():
            if driver.overtake_cooldown_s > 0.0:
                driver.overtake_cooldown_s = max(0.0, driver.overtake_cooldown_s - delta_time)

    def _evaluate_pit_stops(self) -> None:
        """Avalia a heurística de pit stop e aplica a parada (perda do Contrato D4).

        A heurística aceita dicts, então o motor passa adaptadores com os dados
        que os dataclasses de domínio não carregam (clima e contexto do rival
        imediatamente atrás), sem alterar `RaceState`/`DriverState`.
        """
        ativos = sorted(
            (driver for driver in self.state.drivers.values() if not driver.is_retired),
            key=lambda driver: driver.position,
        )
        posicoes = {driver.driver_id: idx for idx, driver in enumerate(ativos)}
        race_adapter = self._strategy_race_state()

        for driver in ativos:
            if driver.pit_status != PitStatus.NONE:
                continue

            # Avalia se deve parar quando estiver na aproximação final da volta
            # (últimos 15% do traçado ou início de volta)
            na_janela_de_pit = (
                driver.lap_distance_covered > 0.85 * self.track_length
                or driver.lap_distance_covered < 0.05 * self.track_length
            )

            if not (na_janela_de_pit and driver.current_lap >= 2):
                continue

            decision = self.pit_heuristic.evaluate_driver(
                driver_state=self._strategy_driver_state(driver, ativos, posicoes),
                race_state=race_adapter,
                pit_lane_loss_s=self.pit_lane_loss_s,
                degradation_curve=self._strategy_degradation_curve,
            )
            if not decision.should_pit:
                continue

            target_name = (decision.target_compound or "medium").upper()
            try:
                novo_composto = TyreCompound[target_name]
            except KeyError:
                novo_composto = TyreCompound.MEDIUM

            driver.pit_status = PitStatus.IN_PIT
            driver.pit_time_remaining = self.pit_lane_loss_s
            driver.pit_stops_made += 1
            self._last_pit_lap[driver.driver_id] = driver.current_lap
            driver.pit_stop_in_this_lap = True
            driver.pit_time_in_this_lap = self.pit_lane_loss_s
            driver.tyre_compound = novo_composto
            driver.tyre_age = 0

            self._queue_event(
                "PIT_STOP",
                [driver.driver_id],
                (
                    f"{driver.name} ({driver.team}) realizou pit stop "
                    f"e colocou pneus {target_name} ({decision.reason})."
                ),
                zone_id="pit_lane",
            )

    def _strategy_degradation_curve(self, compound: str, age_laps: int) -> float:
        """Projeção de degradação da heurística, com proxy para compostos de chuva."""
        name = str(compound).strip().lower()
        return tyre_time_loss(
            STRATEGY_DEGRADATION_PROXY.get(name, name),  # type: ignore[arg-type]
            age_laps,
            self.track_temp,
        )

    def _strategy_race_state(self) -> dict[str, Any]:
        """`RaceState` adaptado ao contrato de entrada da heurística de estratégia."""
        return {
            "current_lap": self.state.current_lap,
            "total_laps": self.state.total_laps,
            "track_status": self.state.track_status,
            "weather": self.heuristic_weather,
            # VSC chega como YELLOW (Contrato D2); só o SC pleno libera a parada barata.
            "safety_car": self.state.track_status == TrackStatus.SAFETY_CAR,
            "red_flag": self.state.track_status == TrackStatus.RED,
        }

    def _strategy_driver_state(
        self,
        driver: DriverState,
        ativos: list[DriverState],
        posicoes: dict[str, int],
    ) -> dict[str, Any]:
        """`DriverState` adaptado, com o contexto do rival imediatamente atrás."""
        indice = posicoes.get(driver.driver_id, -1)
        rival = ativos[indice + 1] if 0 <= indice < len(ativos) - 1 else None
        ultima_parada = self._last_pit_lap.get(rival.driver_id) if rival else None

        return {
            "team": driver.team,
            "tyre_compound": driver.tyre_compound,
            "tyre_age": driver.tyre_age,
            "current_lap": driver.current_lap,
            # O gap do rival até este piloto é o `gap_to_ahead` do próprio rival.
            "gap_to_car_behind": rival.gap_to_ahead if rival else None,
            "rival_behind_pitted": bool(
                rival
                and (
                    rival.pit_status != PitStatus.NONE
                    or (
                        ultima_parada is not None
                        and driver.current_lap - ultima_parada <= UNDERCUT_WINDOW_LAPS
                    )
                )
            ),
        }

    def _resolve_overtakes(self) -> None:
        """Sorteia ultrapassagens do tick e emite os eventos correspondentes."""
        if self.track_map is None:
            return

        resultados = sample_overtake(
            self.state,
            self.track_map,
            self.rng,
            track_temp=self.track_temp,
        )
        for resultado in resultados:
            atacante = self.state.drivers.get(resultado.attacker_id)
            defensor = self.state.drivers.get(resultado.defender_id)
            nome_atacante = atacante.name if atacante else resultado.attacker_id
            nome_defensor = defensor.name if defensor else resultado.defender_id
            self._queue_event(
                "OVERTAKE",
                [resultado.attacker_id, resultado.defender_id],
                (
                    f"{nome_atacante} ultrapassou {nome_defensor} em "
                    f"{resultado.zone_id} (gap {resultado.gap_s:.3f}s, "
                    f"delta de ritmo {resultado.pace_delta_s:+.3f}s/volta)."
                ),
                zone_id=resultado.zone_id,
            )

    def _sample_lap_incidents(self, laps_before: dict[str, int]) -> list[RaceIncident]:
        """Amostra incidentes para cada piloto que cruzou a linha neste tick."""
        if self.track_map is None:
            return []

        incidents: list[RaceIncident] = []
        for driver in self.state.drivers.values():
            if driver.is_retired:
                continue
            anterior = laps_before.get(driver.driver_id, driver.current_lap)
            if driver.current_lap <= anterior:
                continue

            grip = tyre_grip(
                compound_name(driver),  # type: ignore[arg-type]
                driver.tyre_age,
                self.track_temp,
            )
            incident = sample_driver_lap_incident(
                driver.driver_id,
                driver.current_lap,
                self.track_map,
                self.rng,
                grip_factor=max(0.3, min(1.0, grip)),
                weather=self.incident_weather,  # type: ignore[arg-type]
                aggression=self._aggression_for(driver.team),
            )
            if incident is not None:
                incidents.append(incident)
        return incidents

    def _apply_incident(self, incident: RaceIncident) -> None:
        """Aplica consequência mecânica do incidente e enfileira `event_update`."""
        driver = self.state.drivers.get(incident.driver_id)
        if driver is None:
            return

        # Perda de tempo local (travada/escapada) imobiliza/atrasa o piloto na pista.
        driver.incident_time_remaining += incident.time_loss_s

        local = incident.corner_name or f"setor {incident.sector}"
        if incident.consequence == "SC":
            consequencia = "Safety Car acionado"
        elif incident.consequence == "VSC":
            consequencia = "Virtual Safety Car acionado"
        else:
            consequencia = f"perda de {incident.time_loss_s:.1f}s"

        zone_id = f"track:{int(incident.distance_m)}m"

        if incident.caused_retirement:
            driver.is_retired = True
            driver.pit_status = PitStatus.NONE
            driver.pit_time_remaining = 0.0
            self._queue_event(
                "RETIREMENT",
                [driver.driver_id],
                (
                    f"{driver.name} ({driver.team}) abandonou após incidente em {local} "
                    f"(escapatória de {incident.runoff})."
                ),
                zone_id=zone_id,
                lap=incident.lap_number,
            )

        self._queue_event(
            "ACCIDENT",
            [driver.driver_id],
            (
                f"{driver.name} ({driver.team}) teve incidente em {local} "
                f"(severidade {incident.severity or 'desconhecida'}, "
                f"escapatória de {incident.runoff}): {consequencia}."
            ),
            zone_id=zone_id,
            lap=incident.lap_number,
        )

    def _on_new_race_lap(self, incidents: list[RaceIncident]) -> None:
        """Avança a direção de prova ao fim de uma volta da corrida."""
        anterior = self.race_control.state
        self.race_control.advance_lap()
        if incidents:
            self.race_control.trigger_from_incidents(incidents, self.rng)
        self._sync_track_status(anterior, incidents)

    def _sync_track_status(self, previous: str, incidents: list[RaceIncident]) -> None:
        """Espelha o estado da direção de prova no `track_status` do Contrato D2."""
        atual = self.race_control.state
        self.state.track_status = RACE_CONTROL_TO_TRACK_STATUS[atual]

        if atual == previous:
            return

        envolvidos = [i.driver_id for i in incidents]
        if self.state.track_status == TrackStatus.SAFETY_CAR:
            self._compress_field()
            self._queue_event(
                "SAFETY_CAR_DEPLOYED",
                envolvidos,
                ("Safety Car acionado. Pelotão comprimido e DRS desabilitado até a relargada."),
            )
        elif self.state.track_status == TrackStatus.YELLOW:
            self._queue_event(
                "VSC_DEPLOYED",
                envolvidos,
                "Virtual Safety Car acionado. Ritmo reduzido em toda a pista.",
            )
        elif self.state.track_status == TrackStatus.GREEN:
            self._queue_event(
                "GREEN_FLAG",
                [],
                "Pista liberada. Corrida retomada em ritmo normal.",
            )

    def _compress_field(self) -> None:
        """Comprime o pelotão na fila do Safety Car (Contrato D4 / `sim.events`)."""
        ativos = sorted(
            (d for d in self.state.drivers.values() if not d.is_retired),
            key=lambda d: d.position,
        )
        if len(ativos) < 2 or self.track_length <= 0.0:
            return

        lider = ativos[0]
        gaps = SafetyCarStateMachine.compress_gaps([d.position for d in ativos])
        v_ref = max(1.0, lider.base_velocity)

        for (gap_lider, gap_ahead), driver in zip(gaps[1:], ativos[1:], strict=True):
            driver.gap_to_leader = gap_lider
            if gap_ahead is not None:
                driver.gap_to_ahead = gap_ahead

            janela_m = gap_lider * v_ref
            if driver.current_lap == lider.current_lap:
                if lider.lap_distance_covered >= janela_m:
                    distancia = lider.lap_distance_covered - janela_m
                    driver.lap_distance_covered = distancia
                    driver.total_distance_covered = lider.total_distance_covered - janela_m
                else:
                    # Carro já cruzou a linha no mesmo tick; permanece
                    # à frente da linha sem wrap-around
                    fator = gap_lider / (len(ativos) * 10.0 + 1.0)
                    distancia = max(
                        0.1,
                        min(
                            driver.lap_distance_covered, lider.lap_distance_covered * (1.0 - fator)
                        ),
                    )
                    driver.lap_distance_covered = distancia
                    driver.total_distance_covered = (
                        lider.current_lap * self.track_length + distancia
                    )
            else:
                # Caso comum: carro ainda está na volta anterior à do líder
                target_total = max(0.0, lider.total_distance_covered - janela_m)
                driver.total_distance_covered = target_total
                driver.current_lap = int(target_total // self.track_length)
                driver.lap_distance_covered = float(target_total % self.track_length)

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

    async def _deliver_closed_laps(self) -> None:
        """Entrega ao gancho as voltas e eventos acumulados desde a última entrega.

        Roda uma vez por volta do líder, e não por tick: as voltas dos demais
        pilotos fecham em ticks diferentes, então cada lote leva o que fechou no
        intervalo (tipicamente a volta N do líder e a N-1 ou N do resto do pelotão).
        """
        self._race_lap_closed = False
        if self.on_lap_closed is None:
            return

        novas_voltas = self.state.lap_history[self._laps_delivered :]
        self._laps_delivered = len(self.state.lap_history)
        eventos = self._events_since_lap_closed
        self._events_since_lap_closed = []

        if novas_voltas or eventos:
            await self.on_lap_closed(list(novas_voltas), eventos)

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

            # Uma entrega por volta do líder, e a última ao terminar a corrida
            # (os pilotos que cruzam a linha depois do líder ainda fecham voltas).
            if self._race_lap_closed or self.state.is_finished:
                await self._deliver_closed_laps()

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

        if self.state.is_finished and not self.is_stopped and self.on_finished is not None:
            await self.on_finished()
