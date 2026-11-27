"""Ponta a ponta: POST /api/races -> WebSocket -> motor -> banco -> GET /results.

É o teste que faltava para provar o critério do roadmap "uma corrida terminada é
recuperável do banco". Usa o app de verdade (rotas, WebSocket e motor) contra um
PostgreSQL temporário com commit real, como o `test_gravador.py`.
"""

import json
import time
import uuid

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import db_sessao
from app.main import app
from app.websocket import races as ws_races
from db.base import criar_engine
from db.models import LapRecord, Race, RaceEntry
from db.seed import carregar_referencia, popular
from tests.db.helpers import alembic_config, banco_temporario

# Grid de 2024 que existe no seed, cada piloto com a sua equipe padrão.
GRID = ["VER", "NOR", "LEC", "PIA", "SAI", "HAM", "RUS", "PER", "ALO", "STR"]
VOLTAS = 3
PRAZO_S = 60.0


@pytest.fixture(scope="module")
def banco():
    with banco_temporario("corrida_gravada") as url:
        command.upgrade(alembic_config(url), "head")
        eng = criar_engine(url)
        with Session(eng) as s, s.begin():
            popular(s, carregar_referencia())
        yield eng
        eng.dispose()


@pytest.fixture
def cliente(banco, monkeypatch):
    """API e WebSocket apontando para o banco temporário (com commit de verdade)."""
    monkeypatch.setattr(db_sessao, "engine", lambda: banco)
    with TestClient(app) as c:
        yield c


def _criar(cliente: TestClient) -> str:
    resposta = cliente.post(
        "/api/races",
        json={"circuit_id": "monza", "total_laps": VOLTAS, "seed": 7, "grid": GRID,
              "initial_tyres": {"VER": "SOFT"}},
    )  # fmt: skip
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["race_id"]


def _acelerar(race_id: str, anterior: object = None) -> object:
    """Tira a pausa entre ticks do motor atual: a corrida de 3 voltas roda em segundos.

    O motor vive na thread do servidor de teste; num restart ele é trocado logo depois
    de o status virar `running`, então espera aparecer um motor diferente de `anterior`.
    """
    limite = time.monotonic() + PRAZO_S
    while (motor := ws_races.active_engines.get(race_id)) is None or motor is anterior:
        assert time.monotonic() < limite, "o motor da corrida não subiu"
        time.sleep(0.01)
    motor.base_tick_delay = 0.0
    return motor


def _status(banco, race_id: str) -> str:
    with Session(banco) as s:
        return s.get(Race, uuid.UUID(race_id)).status


def _voltas_gravadas(banco, race_id: str) -> int:
    with Session(banco) as s:
        return s.scalar(
            select(func.count())
            .select_from(LapRecord)
            .join(RaceEntry, RaceEntry.id == LapRecord.entry_id)
            .where(RaceEntry.race_id == uuid.UUID(race_id))
        )


def _esperar_status(banco, race_id: str, esperado: str) -> None:
    limite = time.monotonic() + PRAZO_S
    while _status(banco, race_id) != esperado:
        assert time.monotonic() < limite, f"corrida não chegou a {esperado!r} em {PRAZO_S}s"
        time.sleep(0.05)


def test_corrida_criada_pela_api_e_gravada_volta_a_volta(cliente, banco):
    race_id = _criar(cliente)

    with cliente.websocket_connect(f"/ws/races/{race_id}") as ws:
        snapshot = json.loads(ws.receive_text())
        # O grid veio do banco, não do grid padrão do motor.
        assert [d["driver_id"] for d in snapshot["drivers"]] == GRID
        assert snapshot["total_laps"] == VOLTAS
        assert snapshot["drivers"][0]["team"] == "Red Bull Racing"
        assert snapshot["drivers"][0]["tyre_compound"] == "SOFT"
        assert _status(banco, race_id) == "running"

        _acelerar(race_id)
        _esperar_status(banco, race_id, "finished")
        historico = ws_races.active_engines[race_id].state.lap_history

    # Cada volta de cada piloto foi gravada exatamente uma vez.
    assert _voltas_gravadas(banco, race_id) == len(historico) > 0

    resultado = cliente.get(f"/api/races/{race_id}/results").json()
    classificacao = resultado["classification"]
    assert len(classificacao) == len(GRID)
    assert classificacao[0]["total_race_time"] > 0
    detalhes = cliente.get(f"/api/races/{race_id}").json()
    assert detalhes["status"] == "finished" and detalhes["current_lap"] == VOLTAS


def test_restart_regrava_a_corrida_do_zero(cliente, banco):
    race_id = _criar(cliente)

    with cliente.websocket_connect(f"/ws/races/{race_id}") as ws:
        ws.receive_text()
        primeiro_motor = _acelerar(race_id)
        _esperar_status(banco, race_id, "finished")
        primeira = _voltas_gravadas(banco, race_id)

        # O front manda `restart` ao abrir a tela: a mesma corrida roda de novo.
        ws.send_text(json.dumps({"action": "restart", "total_laps": 99}))
        _acelerar(race_id, anterior=primeiro_motor)
        _esperar_status(banco, race_id, "finished")

    # Mesma seed e mesmo grid do banco (o total_laps do payload é ignorado):
    # a corrida regravada tem o mesmo tamanho, sem duplicar nem colidir.
    assert _voltas_gravadas(banco, race_id) == primeira


def test_cliente_que_sai_antes_do_fim_deixa_a_corrida_aborted(cliente, banco):
    race_id = _criar(cliente)

    with cliente.websocket_connect(f"/ws/races/{race_id}") as ws:
        ws.receive_text()

    _esperar_status(banco, race_id, "aborted")


def test_race_id_que_nao_e_uuid_continua_rodando_so_em_memoria(cliente):
    with cliente.websocket_connect("/ws/races/corrida-de-teste") as ws:
        snapshot = json.loads(ws.receive_text())

    assert snapshot["race_id"] == "corrida-de-teste"
    assert len(snapshot["drivers"]) == 20
