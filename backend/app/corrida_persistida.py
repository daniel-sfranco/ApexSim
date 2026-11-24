"""Monta uma corrida do motor a partir do que o `POST /api/races` gravou no banco.

O fluxo combinado (contrato D2) é: o front cria a corrida pela API, recebe o
`race_id` (UUID) e abre `/ws/races/{race_id}`. O WebSocket então carrega grid,
número de voltas, seed e clima daqui, em vez de confiar no que o cliente mandar.

Um `race_id` que não é UUID, ou que não existe no banco, continua funcionando como
antes: corrida só em memória, montada pelo payload do cliente, sem gravação. Isso
mantém o mock, os testes de WebSocket e o front antigo de pé.
"""

import asyncio
import logging
import uuid

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import db_sessao
from db.repositorio import CorridaCarregada, CorridaNaoEncontrada, carregar_corrida
from sim.run import montar_grid_inicial
from sim.state import RaceState

logger = logging.getLogger("apexsim.corrida_persistida")


def interpretar_race_id(race_id: str) -> uuid.UUID | None:
    """O UUID da corrida, ou None se o identificador não for um UUID (corrida em memória)."""
    try:
        return uuid.UUID(race_id)
    except (ValueError, AttributeError, TypeError):
        return None


def _carregar(race_uuid: uuid.UUID) -> CorridaCarregada | None:
    with Session(db_sessao.engine()) as session:
        try:
            return carregar_corrida(session, race_uuid)
        except CorridaNaoEncontrada:
            return None


async def carregar_corrida_do_banco(race_id: str) -> CorridaCarregada | None:
    """Lê a corrida do banco numa thread. None se ela não estiver lá.

    Se o banco estiver fora do ar, registra o erro e devolve None: a corrida ainda
    roda (em memória) em vez de derrubar a conexão do cliente.
    """
    race_uuid = interpretar_race_id(race_id)
    if race_uuid is None:
        return None
    try:
        return await asyncio.to_thread(_carregar, race_uuid)
    except SQLAlchemyError:
        logger.exception(
            "Banco indisponível ao carregar a corrida %s; seguindo sem gravar", race_id
        )
        return None


def estado_inicial(corrida: CorridaCarregada, track_length: float) -> RaceState:
    """`RaceState` de largada com o grid, os pneus e o número de voltas do banco.

    Nome e equipe vêm do banco (ex.: "Red Bull Racing"), que é o mesmo vocabulário
    das cores do front (`F1_TEAMS` em `frontend/src/lib/constants.ts`). O
    `track_length` posiciona o grid atrás da linha de chegada (`montar_grid_inicial`).
    """
    pneus = dict(corrida.config.get("initial_tyres") or {})
    state = montar_grid_inicial(
        grid=[entrada.codigo_piloto for entrada in corrida.grid],
        initial_tyres=pneus,
        track_length=track_length,
    )
    for entrada in corrida.grid:
        piloto = state.drivers[entrada.codigo_piloto]
        piloto.name = entrada.nome_piloto
        piloto.team = entrada.equipe
    state.total_laps = corrida.total_laps
    return state
