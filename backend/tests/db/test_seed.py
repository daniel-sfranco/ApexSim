"""Testes do seed: idempotência e fidelidade aos mapeamentos versionados.

Rodam contra o PostgreSQL real e os CSVs de `data/mapeamentos/` que estão no
repositório, então pegam também um CSV que ficou fora de sincronia com o schema.
"""

import pandas as pd
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import CIRCUITOS, MAPEAMENTOS_DIR
from db.models import Circuit, Driver, Team, TyreCompound
from db.seed import carregar_referencia, popular


@pytest.fixture(scope="module")
def referencia():
    return carregar_referencia()


def _contar(session: Session, modelo) -> int:
    return session.scalar(select(func.count()).select_from(modelo))


def test_seed_em_banco_vazio_cria_toda_a_referencia(session, referencia):
    resumo = popular(session, referencia)

    assert _contar(session, TyreCompound) == len(referencia.compostos)
    assert _contar(session, Circuit) == len(referencia.circuitos)
    assert _contar(session, Driver) == len(referencia.pilotos)
    assert _contar(session, Team) == len(referencia.equipes)
    assert all(t["atualizados"] == 0 and t["inalterados"] == 0 for t in resumo.values())


def test_rodar_duas_vezes_nao_duplica_nem_altera_nada(session, referencia):
    """O critério do roadmap: `make seed` duas vezes não quebra nem duplica."""
    popular(session, referencia)
    antes = {m: _contar(session, m) for m in (TyreCompound, Circuit, Driver, Team)}

    segunda = popular(session, referencia)

    assert {m: _contar(session, m) for m in antes} == antes
    assert all(t["criados"] == 0 and t["atualizados"] == 0 for t in segunda.values())


def test_rodar_de_novo_nao_gasta_ids_da_sequencia(session, referencia):
    popular(session, referencia)
    maior_id = session.scalar(select(func.max(Driver.id)))

    popular(session, referencia)
    popular(session, referencia)

    assert session.scalar(select(func.max(Driver.id))) == maior_id


def test_seed_corrige_o_que_mudou_e_nao_apaga_o_resto(session, referencia):
    popular(session, referencia)
    session.get(Circuit, "monza").name = "Nome errado"
    session.add(Driver(code="ZZZ", full_name="Piloto Fora do Seed"))
    session.flush()

    resumo = popular(session, referencia)

    assert session.get(Circuit, "monza").name != "Nome errado"
    assert resumo["circuits"]["atualizados"] == 1
    assert session.scalar(select(Driver).where(Driver.code == "ZZZ")) is not None


def test_dados_de_referencia_conferem(session, referencia):
    popular(session, referencia)

    assert session.get(Circuit, "interlagos").length_m == 4309
    assert session.get(TyreCompound, "SOFT").name_pt == "Macio"
    assert session.scalar(select(Driver.full_name).where(Driver.code == "VER")) == "Max Verstappen"
    assert session.scalar(select(Team).where(Team.name == "Ferrari")) is not None


def test_so_entram_os_tres_circuitos_do_projeto(session, referencia):
    popular(session, referencia)

    ids = set(session.scalars(select(Circuit.id)))

    assert ids == set(CIRCUITOS)
    for circuito in session.scalars(select(Circuit)):
        assert circuito.length_m == CIRCUITOS[circuito.id].length_m


def test_compostos_desconhecidos_ficam_de_fora(session, referencia):
    popular(session, referencia)

    codigos = set(session.scalars(select(TyreCompound.code)))

    assert codigos == {"SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"}


def test_grid_do_seed_e_de_uma_unica_temporada(referencia):
    """`drivers.code` é UNIQUE: misturar temporadas colidiria em VER, ALB, MAG..."""
    codigos = [p["code"] for p in referencia.pilotos]
    pilotos = pd.read_csv(MAPEAMENTOS_DIR / "pilotos.csv")

    assert len(codigos) == len(set(codigos))
    assert set(codigos) == set(pilotos[pilotos["temporada"] == 2024]["codigo"])
