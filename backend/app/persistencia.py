"""Ponte assíncrona entre o motor de simulação e o banco.

O motor roda em `asyncio` e o driver do PostgreSQL (psycopg) é síncrono: gravar
direto do loop travaria a emissão das voltas. Por isso cada gravação vai para uma
thread (`asyncio.to_thread`), e o motor só espera ela terminar antes da próxima volta.

O `sim/` continua puro: ele não importa nada daqui. Quem monta a corrida entrega
`GravadorDeCorrida.registrar_volta` ao motor como o gancho `on_lap_closed`
(ver `app/websocket/races.py`).

Reinício da mesma corrida
-------------------------
O cliente pode pedir `restart` ou reconectar, e aí a MESMA corrida (mesmo
`race_id`) é simulada de novo por um motor novo, com um gravador novo. O antigo
pode ter uma gravação em voo numa thread, que não dá para cancelar. Duas
proteções evitam que ela suje a corrida nova:

1. Uma trava (`threading.Lock`) por corrida: toda escrita de qualquer gravador
   daquela corrida passa por ela, então a limpeza do histórico (`preparar`) nunca
   se intercala com uma volta do gravador antigo.
2. O gravador antigo é desativado (`desativar`) antes da limpeza; dentro da trava
   ele confere a flag e desiste, se ainda não tinha começado.
"""

import asyncio
import threading
import uuid
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from db import repositorio
from db.repositorio import EventoDeCorrida
from sim.state import LapResult

# Uma trava por corrida, compartilhada por todos os gravadores dela.
_TRAVAS: defaultdict[uuid.UUID, threading.Lock] = defaultdict(threading.Lock)

# Eventos do motor que pertencem a um piloto: o primeiro de `involved_drivers` vira o
# `entry_id` do evento (numa ultrapassagem, o atacante). Os demais tipos (Safety Car,
# VSC, bandeira verde) são da corrida inteira e ficam sem piloto.
EVENTOS_DE_PILOTO = frozenset({"PIT_STOP", "RETIREMENT", "ACCIDENT", "OVERTAKE"})


def eventos_do_motor(envelopes: Iterable[Mapping[str, Any]]) -> list[EventoDeCorrida]:
    """Traduz os envelopes `event_update` (contrato D2) para linhas de `race_events`.

    O `RETIREMENT` do motor é o mesmo `EVENTO_ABANDONO` que o repositório lê para
    calcular o `is_retired`, então não precisa de tratamento à parte. O envelope
    inteiro (pilotos envolvidos, zona e descrição) vai para o `payload`.
    """
    eventos = []
    for envelope in envelopes:
        tipo = str(envelope["event_type"])
        envolvidos = list(envelope.get("involved_drivers") or [])
        piloto = envolvidos[0] if tipo in EVENTOS_DE_PILOTO and envolvidos else None
        eventos.append(
            EventoDeCorrida(
                lap_number=max(0, int(envelope.get("lap") or 0)),
                event_type=tipo,
                codigo_piloto=piloto,
                payload={
                    "involved_drivers": envolvidos,
                    "zone_id": envelope.get("zone_id"),
                    "description": envelope.get("description"),
                },
            )
        )
    return eventos


class GravadorDeCorrida:
    """Grava uma corrida no banco, uma volta por transação."""

    def __init__(self, engine: Engine, race_id: uuid.UUID) -> None:
        self._engine = engine
        self._race_id = race_id
        self._mapa: dict[str, int] | None = None  # código FIA -> race_entries.id
        self._trava = _TRAVAS[race_id]
        self._ativo = True

    @property
    def ativo(self) -> bool:
        """False depois de `desativar` ou de gravar um status final."""
        return self._ativo

    def desativar(self) -> None:
        """Faz as próximas gravações deste gravador virarem no-op (o motor foi trocado).

        É síncrono de propósito: trocar um bool é atômico, e quem chama (o `stop_engine`
        do WebSocket) não pode esperar o banco.
        """
        self._ativo = False

    def _preparar(self) -> None:
        with self._trava, Session(self._engine) as session, session.begin():
            repositorio.limpar_historico(session, self._race_id)
            repositorio.atualizar_status(session, self._race_id, "running")

    async def preparar(self) -> None:
        """Zera o histórico de uma simulação anterior e marca a corrida como `running`."""
        await asyncio.to_thread(self._preparar)

    def _gravar(self, voltas: Sequence[LapResult], eventos: Sequence[EventoDeCorrida]) -> None:
        # Uma transação por volta: se algo falhar, a volta inteira é desfeita.
        with self._trava:
            if not self._ativo:
                return
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
        with self._trava:
            if not self._ativo:
                return
            with Session(self._engine) as session, session.begin():
                repositorio.atualizar_status(session, self._race_id, status)
            if status in ("finished", "aborted"):
                # Depois do status final, nada mais deste gravador entra no banco.
                self._ativo = False

    async def mudar_status(self, status: str) -> None:
        """`running` ao largar; `finished` ou `aborted` ao fim (e aí o gravador se desativa)."""
        await asyncio.to_thread(self._mudar_status, status)
