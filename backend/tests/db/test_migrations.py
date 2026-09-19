"""Testes das migrations do Alembic.

Protegem contra o problema que o roadmap descreve: "sem migrations, cinco
bancos locais divergem em duas semanas".
"""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect

from db.base import Base, criar_engine
from tests.db.helpers import alembic_config, banco_temporario


@pytest.fixture
def banco_vazio():
    """Banco novo por teste: estes testes sobem e descem o schema à vontade."""
    with banco_temporario("migracao") as url:
        yield url


def _tabelas(url: str) -> set[str]:
    engine = criar_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_upgrade_cria_todas_as_tabelas_dos_modelos(banco_vazio):
    command.upgrade(alembic_config(banco_vazio), "head")

    assert _tabelas(banco_vazio) == set(Base.metadata.tables) | {"alembic_version"}


def test_downgrade_remove_tudo_e_upgrade_funciona_de_novo(banco_vazio):
    """Toda migration precisa ser reversível, e refazer o caminho não pode quebrar."""
    cfg = alembic_config(banco_vazio)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    assert _tabelas(banco_vazio) == {"alembic_version"}

    command.upgrade(cfg, "head")
    assert _tabelas(banco_vazio) == set(Base.metadata.tables) | {"alembic_version"}


def test_modelos_e_migrations_estao_em_sincronia(banco_vazio):
    """Falha se alguém editou db/models.py e esqueceu de gerar a migration.

    Corrija com `make migration m="descrição"`.
    """
    command.upgrade(alembic_config(banco_vazio), "head")

    engine = criar_engine(banco_vazio)
    try:
        with engine.connect() as conexao:
            contexto = MigrationContext.configure(conexao, opts={"compare_type": True})
            diferencas = compare_metadata(contexto, Base.metadata)
    finally:
        engine.dispose()

    assert diferencas == [], f"modelos divergem das migrations: {diferencas}"


def test_ha_uma_unica_cabeca_de_migration():
    """Duas pessoas criando migration em paralelo geram duas cabeças (histórico bifurcado).

    Se falhar: `alembic merge heads` ou rebaseie a sua migration sobre a mais recente.
    """
    scripts = ScriptDirectory.from_config(alembic_config("postgresql+psycopg://x/x"))

    assert len(scripts.get_heads()) == 1, f"cabeças de migration: {scripts.get_heads()}"
