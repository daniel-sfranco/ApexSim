"""Consultas e gravações que o motor e a API fazem sobre o banco.

Traduz o que o resto do sistema fala (código FIA do piloto, slug do circuito,
nome da equipe) para as chaves do banco. Não dá commit: a transação é de quem
chama, e um erro no meio desfaz tudo.

O motor emite `driver_id` como código FIA ("VER"); as voltas gravadas apontam
para `race_entries.id`. `mapa_entradas` faz essa ponte uma vez por corrida, em
vez de uma consulta por volta.
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from db.models import (
    EVENTO_ABANDONO,
    STATUS_DA_CORRIDA,
    Circuit,
    Driver,
    LapRecord,
    Race,
    RaceEntry,
    RaceEvent,
    Team,
)
from sim.state import LapResult


class ReferenciaDesconhecida(LookupError):
    """Um circuito, piloto ou equipe que não existe no banco (falta rodar `make seed`?)."""


class CorridaNaoEncontrada(LookupError):
    """Não há corrida com este `race_id`."""


@dataclass(frozen=True)
class InscricaoNoGrid:
    """Quem larga e de que posição. A `equipe` é opcional: sem ela vale a do piloto no seed."""

    codigo_piloto: str
    posicao_no_grid: int
    equipe: str | None = None


def criar_corrida(
    session: Session,
    *,
    circuit_id: str,
    seed: int,
    total_laps: int,
    config: Mapping[str, Any],
    grid: Sequence[InscricaoNoGrid],
) -> Race:
    """Cria a corrida e as inscrições do grid. Falha antes de gravar se algo não existir."""
    if session.get(Circuit, circuit_id) is None:
        raise ReferenciaDesconhecida(f"circuito desconhecido: {circuit_id!r}")

    pilotos = {
        d.code: d
        for d in session.scalars(
            select(Driver).where(Driver.code.in_(i.codigo_piloto for i in grid))
        )
    }
    equipes = {
        t.name: t.id
        for t in session.scalars(
            select(Team).where(Team.name.in_(i.equipe for i in grid if i.equipe))
        )
    }
    faltam_pilotos = sorted({i.codigo_piloto for i in grid} - set(pilotos))
    faltam_equipes = sorted({i.equipe for i in grid if i.equipe} - set(equipes))
    if faltam_pilotos or faltam_equipes:
        raise ReferenciaDesconhecida(
            f"pilotos desconhecidos: {faltam_pilotos}; equipes desconhecidas: {faltam_equipes}"
        )
    equipe_de = {}
    for i in grid:
        id_da_equipe = equipes[i.equipe] if i.equipe else pilotos[i.codigo_piloto].team_id
        if id_da_equipe is None:
            raise ReferenciaDesconhecida(
                f"piloto {i.codigo_piloto} não tem equipe padrão: informe a equipe no grid"
            )
        equipe_de[i.codigo_piloto] = id_da_equipe

    corrida = Race(circuit_id=circuit_id, seed=seed, total_laps=total_laps, config=dict(config))
    session.add(corrida)
    session.flush()  # gera o UUID da corrida
    session.add_all(
        RaceEntry(
            race_id=corrida.id,
            driver_id=pilotos[i.codigo_piloto].id,
            team_id=equipe_de[i.codigo_piloto],
            grid_position=i.posicao_no_grid,
        )
        for i in grid
    )
    session.flush()
    return corrida


def mapa_entradas(session: Session, race_id: uuid.UUID) -> dict[str, int]:
    """Código FIA do piloto -> `race_entries.id`, para gravar as voltas em lote."""
    linhas = session.execute(
        select(Driver.code, RaceEntry.id)
        .join(RaceEntry, RaceEntry.driver_id == Driver.id)
        .where(RaceEntry.race_id == race_id)
    )
    return {codigo: entry_id for codigo, entry_id in linhas}


# ---------------------------------------------------------------------------
# Persistência em lote: uma vez por volta, nunca a cada tick
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EventoDeCorrida:
    """Um evento a gravar em `race_events`. `codigo_piloto` é nulo em evento global."""

    lap_number: int
    event_type: str
    codigo_piloto: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)


def _entrada_do_piloto(mapa: Mapping[str, int], codigo: str) -> int:
    try:
        return mapa[codigo]
    except KeyError:
        raise ReferenciaDesconhecida(
            f"piloto {codigo!r} não está inscrito nesta corrida (mapa: {sorted(mapa)})"
        ) from None


def gravar_voltas(session: Session, mapa: Mapping[str, int], voltas: Sequence[LapResult]) -> int:
    """Grava as voltas de um fechamento de volta (tipicamente 20 linhas) num único INSERT.

    `mapa` é o resultado de `mapa_entradas`. Um piloto fora do mapa derruba a gravação
    inteira antes de enviar qualquer linha, e o banco recusa volta duplicada, tempo
    inválido ou composto inexistente. Devolve quantas linhas gravou.
    """
    if not voltas:
        return 0
    linhas = [
        {
            "entry_id": _entrada_do_piloto(mapa, v.driver_id),
            "lap_number": v.lap_number,
            "lap_time_s": v.lap_time,
            "position": v.position,
            "gap_to_leader_s": v.gap_to_leader,
            "gap_to_ahead_s": v.gap_to_ahead,
            "tyre_compound_code": v.tyre_compound.name,
            "tyre_age_laps": v.tyre_age,
            "fuel_load_kg": v.fuel_load,
            "pit_stop": v.pit_stop,
            "pit_time_s": v.pit_time,
        }
        for v in voltas
    ]
    session.execute(insert(LapRecord), linhas)
    return len(linhas)


def gravar_eventos(
    session: Session,
    race_id: uuid.UUID,
    mapa: Mapping[str, int],
    eventos: Sequence[EventoDeCorrida],
) -> int:
    """Grava eventos de corrida. Evento sem piloto fica sem `entry_id` (ex.: Safety Car)."""
    if not eventos:
        return 0
    linhas = [
        {
            "race_id": race_id,
            "lap_number": e.lap_number,
            "entry_id": _entrada_do_piloto(mapa, e.codigo_piloto) if e.codigo_piloto else None,
            "event_type": e.event_type,
            "payload": dict(e.payload),
        }
        for e in eventos
    ]
    session.execute(insert(RaceEvent), linhas)
    return len(linhas)


def registrar_abandono(
    session: Session,
    race_id: uuid.UUID,
    mapa: Mapping[str, int],
    codigo_piloto: str,
    lap_number: int,
) -> None:
    """Registra que o piloto abandonou. É daqui que o `is_retired` do contrato D2 sai."""
    gravar_eventos(
        session, race_id, mapa, [EventoDeCorrida(lap_number, EVENTO_ABANDONO, codigo_piloto)]
    )


def atualizar_status(
    session: Session, race_id: uuid.UUID, status: str, finished_at: datetime | None = None
) -> Race:
    """Muda o estado da corrida. Ao terminar ou abortar, grava `finished_at` (agora, se omitido)."""
    if status not in STATUS_DA_CORRIDA:
        raise ValueError(f"status inválido {status!r}; válidos: {STATUS_DA_CORRIDA}")
    corrida = session.get(Race, race_id)
    if corrida is None:
        raise CorridaNaoEncontrada(str(race_id))
    corrida.status = status
    if status in ("finished", "aborted"):
        corrida.finished_at = finished_at or datetime.now(UTC)
    else:
        # Corrida que volta a rodar (reinício) deixa de ter um fim registrado.
        corrida.finished_at = None
    session.flush()
    return corrida


def limpar_historico(session: Session, race_id: uuid.UUID) -> None:
    """Apaga as voltas e os eventos gravados, mantendo a corrida e o grid.

    Usado quando a mesma corrida é simulada de novo (o cliente pede `restart` ou
    reconecta): sem isso, a segunda simulação colidiria com a primeira na
    unicidade de (`entry_id`, `lap_number`).
    """
    entradas = select(RaceEntry.id).where(RaceEntry.race_id == race_id)
    session.execute(delete(LapRecord).where(LapRecord.entry_id.in_(entradas)))
    session.execute(delete(RaceEvent).where(RaceEvent.race_id == race_id))
    session.flush()


@dataclass(frozen=True)
class EntradaDoGrid:
    """Uma inscrição já resolvida: quem é, por qual equipe e de onde larga."""

    entry_id: int
    codigo_piloto: str
    nome_piloto: str
    equipe: str
    posicao_no_grid: int


@dataclass(frozen=True)
class CorridaCarregada:
    """O que o motor precisa para montar a corrida a partir do `race_id`."""

    race_id: uuid.UUID
    circuit_id: str
    seed: int
    total_laps: int
    status: str
    config: Mapping[str, Any]
    grid: tuple[EntradaDoGrid, ...]


def carregar_corrida(session: Session, race_id: uuid.UUID) -> CorridaCarregada:
    """Lê a corrida e o grid ordenado por posição de largada.

    É o contrato entre a API e o motor: o `POST /api/races` só grava, e o WebSocket
    carrega por aqui, então nenhum dos dois guarda a corrida em memória do outro.
    """
    corrida = session.get(Race, race_id)
    if corrida is None:
        raise CorridaNaoEncontrada(str(race_id))
    linhas = session.execute(
        select(RaceEntry.id, Driver.code, Driver.full_name, Team.name, RaceEntry.grid_position)
        .join(Driver, Driver.id == RaceEntry.driver_id)
        .join(Team, Team.id == RaceEntry.team_id)
        .where(RaceEntry.race_id == race_id)
        .order_by(RaceEntry.grid_position)
    )
    return CorridaCarregada(
        race_id=corrida.id,
        circuit_id=corrida.circuit_id,
        seed=corrida.seed,
        total_laps=corrida.total_laps,
        status=corrida.status,
        config=corrida.config,
        grid=tuple(EntradaDoGrid(*linha) for linha in linhas),
    )
