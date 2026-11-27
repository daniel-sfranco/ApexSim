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
    InscricaoNoGrid("VER", 1, "Red Bull Racing"),
    InscricaoNoGrid("NOR", 2, "McLaren"),
    InscricaoNoGrid("LEC", 3, "Ferrari"),
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
        ({"grid": [InscricaoNoGrid("XXX", 1, "Ferrari")]}, "['XXX']"),
        ({"grid": [InscricaoNoGrid("VER", 1, "Equipe Fantasma")]}, "['Equipe Fantasma']"),
    ],
)
def test_referencia_inexistente_falha_alto_sem_gravar_nada(semeado, mudanca, trecho):
    with pytest.raises(
        ReferenciaDesconhecida, match=trecho.replace("[", r"\[").replace("]", r"\]")
    ):
        _criar(semeado, **mudanca)

    assert semeado.scalar(select(func.count()).select_from(Race)) == 0
    assert semeado.scalar(select(func.count()).select_from(RaceEntry)) == 0


def test_grid_so_com_codigos_usa_a_equipe_padrao_do_piloto(semeado):
    """O contrato D2 manda só os códigos; a equipe vem de drivers.team_id."""
    corrida = _criar(
        semeado,
        grid=[InscricaoNoGrid("VER", 1), InscricaoNoGrid("HAM", 2), InscricaoNoGrid("BEA", 3)],
    )

    mapa = mapa_entradas(semeado, corrida.id)

    assert semeado.get(RaceEntry, mapa["VER"]).team.name == "Red Bull Racing"
    assert semeado.get(RaceEntry, mapa["HAM"]).team.name == "Mercedes"
    assert (
        semeado.get(RaceEntry, mapa["BEA"]).team.name == "Haas F1 Team"
    )  # mais voltas que na Ferrari


def test_equipe_informada_no_grid_vence_a_padrao(semeado):
    corrida = _criar(semeado, grid=[InscricaoNoGrid("BEA", 1, "Ferrari")])

    entrada = semeado.get(RaceEntry, mapa_entradas(semeado, corrida.id)["BEA"])

    assert entrada.team.name == "Ferrari"


def test_piloto_sem_equipe_padrao_e_recusado_sem_gravar(semeado):
    from db.models import Driver

    semeado.add(Driver(code="ZZZ", full_name="Sem Equipe"))
    semeado.flush()

    with pytest.raises(ReferenciaDesconhecida, match="ZZZ"):
        _criar(semeado, grid=[InscricaoNoGrid("ZZZ", 1)])

    assert semeado.scalar(select(func.count()).select_from(Race)) == 0
