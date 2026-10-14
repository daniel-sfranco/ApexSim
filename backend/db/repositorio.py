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
