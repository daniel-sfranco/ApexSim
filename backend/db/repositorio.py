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
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Circuit, Driver, Race, RaceEntry, Team


class ReferenciaDesconhecida(LookupError):
    """Um circuito, piloto ou equipe que não existe no banco (falta rodar `make seed`?)."""


@dataclass(frozen=True)
class InscricaoNoGrid:
    """Quem larga, por qual equipe e de que posição."""

    codigo_piloto: str
    equipe: str
    posicao_no_grid: int


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
        d.code: d.id
        for d in session.scalars(
            select(Driver).where(Driver.code.in_(i.codigo_piloto for i in grid))
        )
    }
    equipes = {
        t.name: t.id
        for t in session.scalars(select(Team).where(Team.name.in_(i.equipe for i in grid)))
    }
    faltam_pilotos = sorted({i.codigo_piloto for i in grid} - set(pilotos))
    faltam_equipes = sorted({i.equipe for i in grid} - set(equipes))
    if faltam_pilotos or faltam_equipes:
        raise ReferenciaDesconhecida(
            f"pilotos desconhecidos: {faltam_pilotos}; equipes desconhecidas: {faltam_equipes}"
        )

    corrida = Race(circuit_id=circuit_id, seed=seed, total_laps=total_laps, config=dict(config))
    session.add(corrida)
    session.flush()  # gera o UUID da corrida
    session.add_all(
        RaceEntry(
            race_id=corrida.id,
            driver_id=pilotos[i.codigo_piloto],
            team_id=equipes[i.equipe],
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
