"""Ponte assíncrona entre o motor de simulação e o banco.

O motor roda em `asyncio` e o driver do PostgreSQL (psycopg) é síncrono: gravar
direto do loop travaria a emissão das voltas. Por isso cada gravação vai para uma
thread (`asyncio.to_thread`), e o motor só espera ela terminar antes da próxima volta.

O `sim/` continua puro: ele não importa nada daqui. Quem monta a corrida entrega
`GravadorDeCorrida.registrar_volta` ao motor como o callback "uma vez por volta".
"""

import asyncio
import uuid
from collections.abc import Sequence

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from db import repositorio
from db.repositorio import EventoDeCorrida
from sim.state import LapResult


class GravadorDeCorrida:
    """Grava uma corrida no banco, uma volta por transação."""

    def __init__(self, engine: Engine, race_id: uuid.UUID) -> None:
        self._engine = engine
        self._race_id = race_id
        self._mapa: dict[str, int] | None = None  # código FIA -> race_entries.id

    def _gravar(self, voltas: Sequence[LapResult], eventos: Sequence[EventoDeCorrida]) -> None:
        # Uma transação por volta: se algo falhar, a volta inteira é desfeita.
        with Session(self._engine) as session, session.begin():
            if self._mapa is None:  # uma consulta por corrida, não por volta
                self._mapa = repositorio.mapa_entradas(session, self._race_id)
            repositorio.gravar_voltas(session, self._mapa, voltas)
            repositorio.gravar_eventos(session, self._race_id, self._mapa, eventos)

    async def registrar_volta(
        self, voltas: Sequence[LapResult], eventos: Sequence[EventoDeCorrida] = ()
    ) -> None:
        """Grava o fechamento de uma volta. O motor deve dar `await` antes de seguir."""
        await asyncio.to_thread(self._gravar, voltas, eventos)

    def _mudar_status(self, status: str) -> None:
        with Session(self._engine) as session, session.begin():
            repositorio.atualizar_status(session, self._race_id, status)

    async def mudar_status(self, status: str) -> None:
        """`running` ao largar; `finished` ou `aborted` ao fim."""
        await asyncio.to_thread(self._mudar_status, status)
