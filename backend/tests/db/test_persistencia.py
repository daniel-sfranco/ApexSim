"""Testes da gravação em lote: voltas, eventos, abandono, status e leitura da corrida."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from db.models import EVENTO_ABANDONO, LapRecord, RaceEvent
from db.repositorio import (
    CorridaNaoEncontrada,
    EventoDeCorrida,
    InscricaoNoGrid,
    ReferenciaDesconhecida,
    atualizar_status,
    carregar_corrida,
    criar_corrida,
    gravar_eventos,
    gravar_voltas,
    mapa_entradas,
    registrar_abandono,
)
from db.seed import carregar_referencia, popular
from sim.state import LapResult, TyreCompound

CODIGOS = ["VER", "NOR", "LEC", "PIA", "SAI", "HAM"]


@pytest.fixture
def corrida(session):
    popular(session, carregar_referencia())
    grid = [InscricaoNoGrid(c, i + 1) for i, c in enumerate(CODIGOS)]
    return criar_corrida(
        session, circuit_id="monza", seed=42, total_laps=53, config={"clima": "seco"}, grid=grid
    )


@pytest.fixture
def mapa(session, corrida):
    return mapa_entradas(session, corrida.id)


def _volta(codigo, numero=1, **campos) -> LapResult:
    valores = dict(
        driver_id=codigo, lap_number=numero, lap_time=82.5, position=1, gap_to_leader=0.0,
        gap_to_ahead=None, tyre_compound=TyreCompound.MEDIUM, tyre_age=numero,
        fuel_load=100.0, pit_stop=False, pit_time=None,
    )  # fmt: skip
    valores.update(campos)
    return LapResult(**valores)


def _contar(session, modelo) -> int:
    return session.scalar(select(func.count()).select_from(modelo))


# --- voltas -----------------------------------------------------------------


def test_uma_volta_de_seis_pilotos_vira_seis_linhas_com_os_campos_certos(session, mapa):
    voltas = [_volta(c, 1, position=i + 1, gap_to_leader=float(i)) for i, c in enumerate(CODIGOS)]

    gravadas = gravar_voltas(session, mapa, voltas)

    assert gravadas == 6
    linha = session.scalars(select(LapRecord).where(LapRecord.entry_id == mapa["LEC"])).one()
    assert (linha.lap_number, linha.position, linha.gap_to_leader_s) == (1, 3, 2.0)
    assert linha.lap_time_s == 82.5 and linha.fuel_load_kg == 100.0
    assert linha.tyre_compound_code == "MEDIUM" and linha.tyre_age_laps == 1
    assert linha.pit_stop is False and linha.pit_time_s is None and linha.gap_to_ahead_s is None


def test_parada_no_box_grava_o_tempo_e_o_composto_novo(session, mapa):
    parada = _volta(
        "VER", 20, pit_stop=True, pit_time=22.4, tyre_compound=TyreCompound.HARD, tyre_age=0
    )
    gravar_voltas(session, mapa, [parada])

    linha = session.scalars(select(LapRecord)).one()

    assert linha.pit_stop is True and linha.pit_time_s == 22.4
    assert linha.tyre_compound_code == "HARD"


def test_composto_unknown_do_contrato_pode_ser_gravado(session, mapa):
    gravar_voltas(session, mapa, [_volta("VER", tyre_compound=TyreCompound.UNKNOWN)])

    assert session.scalars(select(LapRecord.tyre_compound_code)).one() == "UNKNOWN"


def test_lista_vazia_nao_grava_nada(session, mapa):
    assert gravar_voltas(session, mapa, []) == 0
    assert _contar(session, LapRecord) == 0


def test_piloto_fora_da_corrida_derruba_o_lote_inteiro_antes_de_gravar(session, mapa):
    voltas = [_volta("VER"), _volta("ALO")]  # ALO existe no seed, mas não largou nesta corrida

    with pytest.raises(ReferenciaDesconhecida, match="ALO"):
        gravar_voltas(session, mapa, voltas)

    assert _contar(session, LapRecord) == 0


def test_volta_duplicada_e_recusada_pelo_banco(session, mapa):
    gravar_voltas(session, mapa, [_volta("VER", 3)])

    with pytest.raises(IntegrityError):
        with session.begin_nested():
            gravar_voltas(session, mapa, [_volta("VER", 3)])


def test_tempo_de_volta_invalido_e_recusado_pelo_banco(session, mapa):
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            gravar_voltas(session, mapa, [_volta("VER", lap_time=0.0)])


def test_uma_volta_ruim_no_meio_do_lote_nao_grava_as_outras(session, mapa):
    """Um INSERT só: ou entram as 6, ou nenhuma."""
    voltas = [_volta(c, 1) for c in CODIGOS]
    voltas[3] = _volta("PIA", 1, position=0)  # posição inválida (CHECK)

    with pytest.raises(IntegrityError):
        with session.begin_nested():
            gravar_voltas(session, mapa, voltas)

    assert _contar(session, LapRecord) == 0


# --- eventos e abandono -------------------------------------------------------


def test_evento_global_e_evento_de_piloto(session, corrida, mapa):
    eventos = [
        EventoDeCorrida(12, "SAFETY_CAR_DEPLOYED", payload={"zona": "s_do_senna_brake"}),
        EventoDeCorrida(12, "CRASH", "NOR"),
    ]

    assert gravar_eventos(session, corrida.id, mapa, eventos) == 2

    por_tipo = {e.event_type: e for e in session.scalars(select(RaceEvent))}
    assert por_tipo["SAFETY_CAR_DEPLOYED"].entry_id is None
    assert por_tipo["SAFETY_CAR_DEPLOYED"].payload == {"zona": "s_do_senna_brake"}
    assert por_tipo["CRASH"].entry_id == mapa["NOR"]


def test_abandono_vira_evento_com_a_convencao_do_contrato(session, corrida, mapa):
    registrar_abandono(session, corrida.id, mapa, "LEC", 17)

    evento = session.scalars(select(RaceEvent)).one()

    assert evento.event_type == EVENTO_ABANDONO == "RETIREMENT"
    assert (evento.lap_number, evento.entry_id) == (17, mapa["LEC"])


def test_evento_de_piloto_desconhecido_e_recusado(session, corrida, mapa):
    with pytest.raises(ReferenciaDesconhecida, match="XXX"):
        gravar_eventos(session, corrida.id, mapa, [EventoDeCorrida(1, "CRASH", "XXX")])


# --- status -------------------------------------------------------------------


def test_terminar_a_corrida_grava_finished_at(session, corrida):
    antes = datetime.now(UTC)

    atualizar_status(session, corrida.id, "finished")

    session.refresh(corrida)
    assert corrida.status == "finished" and corrida.finished_at >= antes


def test_largar_a_corrida_nao_grava_finished_at(session, corrida):
    atualizar_status(session, corrida.id, "running")

    session.refresh(corrida)
    assert corrida.status == "running" and corrida.finished_at is None


def test_status_invalido_e_corrida_inexistente_falham_alto(session, corrida):
    with pytest.raises(ValueError, match="pausada"):
        atualizar_status(session, corrida.id, "pausada")
    with pytest.raises(CorridaNaoEncontrada):
        atualizar_status(session, uuid.uuid4(), "running")


# --- leitura para o motor -------------------------------------------------------


def test_carregar_corrida_devolve_o_grid_em_ordem_de_largada(session, corrida):
    carregada = carregar_corrida(session, corrida.id)

    assert (carregada.circuit_id, carregada.seed, carregada.total_laps) == ("monza", 42, 53)
    assert carregada.config == {"clima": "seco"} and carregada.status == "configured"
    assert [g.codigo_piloto for g in carregada.grid] == CODIGOS
    primeiro = carregada.grid[0]
    assert (primeiro.nome_piloto, primeiro.equipe, primeiro.posicao_no_grid) == (
        "Max Verstappen", "Red Bull Racing", 1,
    )  # fmt: skip
    assert primeiro.entry_id == mapa_entradas(session, corrida.id)["VER"]


def test_carregar_corrida_inexistente(session):
    with pytest.raises(CorridaNaoEncontrada):
        carregar_corrida(session, uuid.uuid4())
