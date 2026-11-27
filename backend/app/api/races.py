"""Rotas de corrida do contrato D2 (`docs/openapi.json`).

- `POST /api/races`: grava a corrida configurada. NÃO instancia o motor: o WebSocket
  carrega a corrida pelo `race_id` (`db.repositorio.carregar_corrida`), então nada fica
  guardado em memória entre a API e o motor.
- `GET /api/races/{id}`: estado da corrida.
- `GET /api/races/{id}/results`: classificação calculada do histórico gravado no banco.

Os modelos abaixo espelham os esquemas do `openapi.json`; um teste confere que as
respostas continuam batendo com ele.
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db_sessao import obter_sessao
from app.models.track import TrackMap
from db.models import EVENTO_ABANDONO, Circuit, Driver, LapRecord, Race, RaceEntry, RaceEvent, Team
from db.repositorio import (
    InscricaoNoGrid,
    ReferenciaDesconhecida,
    criar_corrida,
)

router = APIRouter()

# Quantos pilotos cabem num grid (`DriverUpdate.position` vai de 1 a 20 no contrato).
MAXIMO_NO_GRID = 20


class CondicaoClimatica(StrEnum):
    DRY = "DRY"
    DAMP = "DAMP"
    WET = "WET"


class Composto(StrEnum):
    SOFT = "SOFT"
    MEDIUM = "MEDIUM"
    HARD = "HARD"
    INTERMEDIATE = "INTERMEDIATE"
    WET = "WET"
    UNKNOWN = "UNKNOWN"


class CriarCorridaRequest(BaseModel):
    """`CreateRaceRequest` do contrato."""

    circuit_id: Annotated[str, Field(pattern=r"^[a-z0-9_]+$", examples=["interlagos"])]
    total_laps: Annotated[int, Field(ge=1, le=100)] = 53
    seed: int = 42
    weather: CondicaoClimatica = CondicaoClimatica.DRY
    track_temp: float = 32.0
    # Opcional no contrato, mas sem grid não há corrida: ver `criar`.
    grid: list[str] | None = None
    initial_tyres: dict[str, Composto] | None = None


class CriarCorridaResponse(BaseModel):
    """`CreateRaceResponse` do contrato."""

    race_id: uuid.UUID
    circuit_id: str
    total_laps: int
    seed: int
    ws_url: str
    status: str


class CorridaDetalhes(BaseModel):
    """`RaceDetailsResponse` do contrato."""

    race_id: uuid.UUID
    circuit_id: str
    current_lap: int
    total_laps: int
    status: str
    created_at: datetime


class ResultadoDoPiloto(BaseModel):
    """`DriverFinalResult` do contrato."""

    position: int
    driver_id: str
    name: str
    team: str
    total_race_time: float
    gap_to_leader: float = 0.0
    pit_stops_made: int
    fastest_lap: float | None = None
    is_retired: bool = False


class ResultadosDaCorrida(BaseModel):
    """`RaceResultsResponse` do contrato."""

    race_id: uuid.UUID
    circuit_id: str
    total_laps: int
    classification: list[ResultadoDoPiloto]


Sessao = Annotated[Session, Depends(obter_sessao)]


@router.post("/api/races", status_code=201, response_model=CriarCorridaResponse)
def criar(corpo: CriarCorridaRequest, session: Sessao) -> CriarCorridaResponse:
    """Cria e configura uma corrida. O motor só entra em cena quando o cliente abre o WebSocket."""
    # O circuito é conferido no banco ANTES do TrackMap.load, que aceita caminhos de arquivo:
    # só slugs que existem em `circuits` chegam lá.
    if session.get(Circuit, corpo.circuit_id) is None:
        raise HTTPException(404, f"circuito desconhecido: {corpo.circuit_id!r}")
    try:
        TrackMap.load(corpo.circuit_id)
    except FileNotFoundError:
        raise HTTPException(404, f"circuito sem mapa de pista: {corpo.circuit_id!r}") from None

    if not corpo.grid:
        raise HTTPException(
            422, "o grid é obrigatório: lista ordenada de códigos FIA dos pilotos que largam"
        )
    if len(corpo.grid) > MAXIMO_NO_GRID or len(set(corpo.grid)) != len(corpo.grid):
        raise HTTPException(
            422, f"o grid tem de ter de 1 a {MAXIMO_NO_GRID} pilotos, sem repetição"
        )
    sobrando = sorted(set(corpo.initial_tyres or {}) - set(corpo.grid))
    if sobrando:
        raise HTTPException(422, f"initial_tyres cita pilotos fora do grid: {sobrando}")

    try:
        corrida = criar_corrida(
            session,
            circuit_id=corpo.circuit_id,
            seed=corpo.seed,
            total_laps=corpo.total_laps,
            config={
                "weather": corpo.weather.value,
                "track_temp": corpo.track_temp,
                "initial_tyres": {k: v.value for k, v in (corpo.initial_tyres or {}).items()},
            },
            grid=[InscricaoNoGrid(codigo, i + 1) for i, codigo in enumerate(corpo.grid)],
        )
    except ReferenciaDesconhecida as erro:
        raise HTTPException(422, str(erro)) from erro

    return CriarCorridaResponse(
        race_id=corrida.id,
        circuit_id=corrida.circuit_id,
        total_laps=corrida.total_laps,
        seed=corrida.seed,
        ws_url=f"/ws/races/{corrida.id}",
        status="configured",
    )


def _corrida_ou_404(session: Session, race_id: uuid.UUID) -> Race:
    corrida = session.get(Race, race_id)
    if corrida is None:
        raise HTTPException(404, "Corrida não encontrada")
    return corrida


@router.get("/api/races/{race_id}", response_model=CorridaDetalhes)
def detalhes(race_id: uuid.UUID, session: Sessao) -> CorridaDetalhes:
    """Estado da corrida. `current_lap` é a maior volta já gravada (0 antes da largada)."""
    corrida = _corrida_ou_404(session, race_id)
    volta_atual = session.scalar(
        select(func.coalesce(func.max(LapRecord.lap_number), 0))
        .join(RaceEntry, RaceEntry.id == LapRecord.entry_id)
        .where(RaceEntry.race_id == race_id)
    )
    return CorridaDetalhes(
        race_id=corrida.id,
        circuit_id=corrida.circuit_id,
        current_lap=volta_atual,
        total_laps=corrida.total_laps,
        status=corrida.status,
        created_at=corrida.created_at,
    )


@router.get("/api/races/{race_id}/results", response_model=ResultadosDaCorrida)
def resultados(race_id: uuid.UUID, session: Sessao) -> ResultadosDaCorrida:
    """Classificação calculada do histórico gravado.

    Ordena por voltas completadas (mais é melhor) e, no empate, por tempo total. O
    `gap_to_leader` é a diferença para o líder **no mesmo número de voltas**: quem foi
    ultrapassado em voltas ou abandonou fica com a diferença na última volta que completou.
    """
    corrida = _corrida_ou_404(session, race_id)
    inscritos = session.execute(
        select(RaceEntry.id, RaceEntry.grid_position, Driver.code, Driver.full_name, Team.name)
        .join(Driver, Driver.id == RaceEntry.driver_id)
        .join(Team, Team.id == RaceEntry.team_id)
        .where(RaceEntry.race_id == race_id)
    ).all()
    voltas = session.execute(
        select(LapRecord.entry_id, LapRecord.lap_number, LapRecord.lap_time_s, LapRecord.pit_stop)
        .join(RaceEntry, RaceEntry.id == LapRecord.entry_id)
        .where(RaceEntry.race_id == race_id)
        .order_by(LapRecord.entry_id, LapRecord.lap_number)
    ).all()
    abandonos = set(
        session.scalars(
            select(RaceEvent.entry_id).where(
                RaceEvent.race_id == race_id,
                RaceEvent.event_type == EVENTO_ABANDONO,
                RaceEvent.entry_id.is_not(None),
            )
        )
    )

    tempos: dict[int, list[float]] = {e.id: [] for e in inscritos}
    paradas: dict[int, int] = {e.id: 0 for e in inscritos}
    for entry_id, _numero, tempo, parou in voltas:
        tempos[entry_id].append(tempo)
        paradas[entry_id] += int(parou)

    # voltas completadas (mais é melhor), tempo total, e por fim a posição de largada
    ordem = sorted(
        inscritos,
        key=lambda e: (-len(tempos[e.id]), sum(tempos[e.id]), e.grid_position),
    )
    lider = tempos[ordem[0].id] if ordem else []

    classificacao = []
    for posicao, e in enumerate(ordem, start=1):
        meus = tempos[e.id]
        total = sum(meus)
        # tempo do líder somente até a volta em que este piloto parou de completar voltas
        no_lider = sum(lider[: len(meus)])
        classificacao.append(
            ResultadoDoPiloto(
                position=posicao,
                driver_id=e.code,
                name=e.full_name,
                team=e.name,
                total_race_time=total,
                gap_to_leader=total - no_lider if meus else 0.0,
                pit_stops_made=paradas[e.id],
                fastest_lap=min(meus) if meus else None,
                is_retired=e.id in abandonos,
            )
        )
    return ResultadosDaCorrida(
        race_id=corrida.id,
        circuit_id=corrida.circuit_id,
        total_laps=corrida.total_laps,
        classification=classificacao,
    )
