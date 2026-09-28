"""Testes do repositório sobre a referência de verdade (seed aplicado)."""

import pytest
from sqlalchemy import func, select

from db.models import Race, RaceEntry
from db.repositorio import (
    InscricaoNoGrid,
    ReferenciaDesconhecida,
    criar_corrida,
    mapa_entradas,
)
from db.seed import carregar_referencia, popular


@pytest.fixture
def semeado(session):
    popular(session, carregar_referencia())
    return session


GRID = [
    InscricaoNoGrid("VER", "Red Bull Racing", 1),
    InscricaoNoGrid("NOR", "McLaren", 2),
    InscricaoNoGrid("LEC", "Ferrari", 3),
]


def _criar(session, **mudancas):
    dados = dict(circuit_id="interlagos", seed=42, total_laps=71, config={"clima": "seco"})
    dados.update(mudancas)
    return criar_corrida(session, grid=dados.pop("grid", GRID), **dados)


def test_corrida_criada_com_uuid_estado_inicial_e_grid(semeado):
    corrida = _criar(semeado)

    semeado.refresh(corrida)  # traz os defaults que o banco preencheu
    assert corrida.status == "configured"
    assert corrida.created_at is not None
    entradas = semeado.scalars(select(RaceEntry).where(RaceEntry.race_id == corrida.id)).all()
    assert sorted(e.grid_position for e in entradas) == [1, 2, 3]


def test_mapa_entradas_liga_codigo_fia_ao_id_da_inscricao(semeado):
    corrida = _criar(semeado)

    mapa = mapa_entradas(semeado, corrida.id)

    assert set(mapa) == {"VER", "NOR", "LEC"}
    entrada_do_ver = semeado.get(RaceEntry, mapa["VER"])
    assert entrada_do_ver.grid_position == 1
    assert entrada_do_ver.team.name == "Red Bull Racing"


def test_mapa_de_corrida_inexistente_e_vazio(semeado):
    import uuid

    assert mapa_entradas(semeado, uuid.uuid4()) == {}


def test_duas_corridas_no_mesmo_circuito_nao_se_misturam(semeado):
    primeira = _criar(semeado, seed=1)
    segunda = _criar(semeado, seed=2)

    assert primeira.id != segunda.id
    assert set(mapa_entradas(semeado, primeira.id).values()).isdisjoint(
        mapa_entradas(semeado, segunda.id).values()
    )


@pytest.mark.parametrize(
    "mudanca, trecho",
    [
        ({"circuit_id": "zandvoort"}, "circuito desconhecido"),
        ({"grid": [InscricaoNoGrid("XXX", "Ferrari", 1)]}, "['XXX']"),
        ({"grid": [InscricaoNoGrid("VER", "Equipe Fantasma", 1)]}, "['Equipe Fantasma']"),
    ],
)
def test_referencia_inexistente_falha_alto_sem_gravar_nada(semeado, mudanca, trecho):
    with pytest.raises(
        ReferenciaDesconhecida, match=trecho.replace("[", r"\[").replace("]", r"\]")
    ):
        _criar(semeado, **mudanca)

    assert semeado.scalar(select(func.count()).select_from(Race)) == 0
    assert semeado.scalar(select(func.count()).select_from(RaceEntry)) == 0
