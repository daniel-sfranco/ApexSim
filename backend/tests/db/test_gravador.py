"""Testes do GravadorDeCorrida, a ponte assíncrona entre o motor e o banco.

Ele dá commit de verdade (uma transação por volta, em outra conexão), então não cabe
no rollback da fixture `session`. Roda num banco temporário próprio.
"""

import asyncio

import pytest
from alembic import command
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.persistencia import GravadorDeCorrida, eventos_do_motor
from db.base import criar_engine
from db.models import EVENTO_ABANDONO, LapRecord, Race, RaceEntry, RaceEvent
from db.repositorio import EventoDeCorrida, InscricaoNoGrid, criar_corrida
from db.seed import carregar_referencia, popular
from sim.state import LapResult, TyreCompound
from tests.db.helpers import alembic_config, banco_temporario

CODIGOS = ["VER", "NOR", "LEC", "PIA"]


@pytest.fixture(scope="module")
def engine():
    with banco_temporario("gravador") as url:
        command.upgrade(alembic_config(url), "head")
        eng = criar_engine(url)
        with Session(eng) as s, s.begin():
            popular(s, carregar_referencia())
        yield eng
        eng.dispose()


@pytest.fixture
def race_id(engine):
    with Session(engine) as s, s.begin():
        grid = [InscricaoNoGrid(c, i + 1) for i, c in enumerate(CODIGOS)]
        return criar_corrida(s, circuit_id="monza", seed=1, total_laps=10, config={}, grid=grid).id


def _volta(codigo, numero, **campos) -> LapResult:
    valores = dict(
        driver_id=codigo, lap_number=numero, lap_time=82.0, position=1, gap_to_leader=0.0,
        gap_to_ahead=None, tyre_compound=TyreCompound.SOFT, tyre_age=numero, fuel_load=90.0,
        pit_stop=False, pit_time=None,
    )  # fmt: skip
    valores.update(campos)
    return LapResult(**valores)


def _linhas(engine, race_id) -> int:
    """Quantas voltas gravadas pertencem a esta corrida."""
    with Session(engine) as s:
        return s.scalar(
            select(func.count())
            .select_from(LapRecord)
            .join(RaceEntry, RaceEntry.id == LapRecord.entry_id)
            .where(RaceEntry.race_id == race_id)
        )


def test_registrar_volta_grava_e_confirma_a_transacao(engine, race_id):
    gravador = GravadorDeCorrida(engine, race_id)

    asyncio.run(gravador.registrar_volta([_volta(c, 1) for c in CODIGOS]))

    assert _linhas(engine, race_id) == 4


def test_varias_voltas_em_sequencia_reaproveitam_o_mapa(engine, race_id, monkeypatch):
    chamadas = []
    original = __import__("db.repositorio", fromlist=["mapa_entradas"]).mapa_entradas
    monkeypatch.setattr(
        "app.persistencia.repositorio.mapa_entradas",
        lambda *a, **k: chamadas.append(1) or original(*a, **k),
    )
    gravador = GravadorDeCorrida(engine, race_id)

    async def corrida():
        for volta in (1, 2, 3):
            await gravador.registrar_volta([_volta(c, volta) for c in CODIGOS])

    asyncio.run(corrida())

    assert _linhas(engine, race_id) == 12
    assert len(chamadas) == 1  # uma consulta por corrida, não por volta


def test_volta_com_erro_e_desfeita_por_inteiro(engine, race_id):
    gravador = GravadorDeCorrida(engine, race_id)
    voltas = [_volta(c, 1) for c in CODIGOS]
    voltas[2] = _volta("LEC", 1, position=0)  # viola o CHECK

    with pytest.raises(Exception):  # noqa: B017 - IntegrityError, embrulhada pelo SQLAlchemy
        asyncio.run(gravador.registrar_volta(voltas))

    assert _linhas(engine, race_id) == 0


def test_eventos_vao_na_mesma_transacao_da_volta(engine, race_id):
    gravador = GravadorDeCorrida(engine, race_id)
    eventos = [EventoDeCorrida(1, "CRASH", "LEC"), EventoDeCorrida(1, "SAFETY_CAR_DEPLOYED")]

    asyncio.run(gravador.registrar_volta([_volta(c, 1) for c in CODIGOS], eventos))

    with Session(engine) as s:
        assert (
            s.scalar(
                select(func.count()).select_from(RaceEvent).where(RaceEvent.race_id == race_id)
            )
            == 2
        )


def test_mudar_status_confirma_a_transacao(engine, race_id):
    gravador = GravadorDeCorrida(engine, race_id)

    asyncio.run(gravador.mudar_status("running"))
    asyncio.run(gravador.mudar_status("finished"))

    with Session(engine) as s:
        corrida = s.get(Race, race_id)
        assert corrida.status == "finished" and corrida.finished_at is not None


def test_a_gravacao_nao_trava_o_loop_do_motor(engine, race_id):
    """O motor continua respondendo enquanto o banco grava: a gravação vai para uma thread."""
    gravador = GravadorDeCorrida(engine, race_id)
    batimentos = []

    async def motor():
        gravando = asyncio.create_task(gravador.registrar_volta([_volta(c, 1) for c in CODIGOS]))
        while not gravando.done():
            batimentos.append(1)
            await asyncio.sleep(0)
        await gravando

    asyncio.run(motor())

    assert len(batimentos) >= 1  # o loop rodou outras coisas enquanto a thread gravava


def test_gravador_desativado_nao_grava_mais_nada(engine, race_id):
    """Num restart o gravador antigo é desativado: uma volta atrasada dele não entra."""
    gravador = GravadorDeCorrida(engine, race_id)
    gravador.desativar()

    asyncio.run(gravador.registrar_volta([_volta(c, 1) for c in CODIGOS]))
    asyncio.run(gravador.mudar_status("aborted"))

    assert _linhas(engine, race_id) == 0
    with Session(engine) as s:
        assert s.get(Race, race_id).status == "configured"


def test_preparar_limpa_a_simulacao_anterior_e_marca_running(engine, race_id):
    antigo = GravadorDeCorrida(engine, race_id)
    asyncio.run(antigo.registrar_volta([_volta(c, 1) for c in CODIGOS]))
    asyncio.run(antigo.mudar_status("finished"))

    novo = GravadorDeCorrida(engine, race_id)
    asyncio.run(novo.preparar())
    asyncio.run(novo.registrar_volta([_volta(c, 1) for c in CODIGOS]))

    assert _linhas(engine, race_id) == 4  # a volta 1 regravada, sem colidir na unicidade
    with Session(engine) as s:
        corrida = s.get(Race, race_id)
        assert corrida.status == "running" and corrida.finished_at is None


def test_status_final_desativa_o_gravador(engine, race_id):
    gravador = GravadorDeCorrida(engine, race_id)

    asyncio.run(gravador.mudar_status("finished"))

    assert gravador.ativo is False


def test_eventos_do_motor_viram_linhas_de_race_events():
    envelopes = [
        {"lap": 3, "event_type": "OVERTAKE", "involved_drivers": ["NOR", "VER"],
         "zone_id": "drs_1", "description": "NOR passou VER"},
        {"lap": 5, "event_type": "SAFETY_CAR_DEPLOYED", "involved_drivers": ["LEC"],
         "zone_id": None, "description": "SC"},
        {"lap": 7, "event_type": "RETIREMENT", "involved_drivers": ["LEC"],
         "zone_id": "track:120m", "description": "abandono"},
    ]  # fmt: skip

    ultrapassagem, safety_car, abandono = eventos_do_motor(envelopes)

    assert (ultrapassagem.lap_number, ultrapassagem.codigo_piloto) == (3, "NOR")  # o atacante
    assert ultrapassagem.payload["involved_drivers"] == ["NOR", "VER"]
    assert safety_car.codigo_piloto is None  # evento da corrida inteira
    assert (abandono.event_type, abandono.codigo_piloto) == (EVENTO_ABANDONO, "LEC")
