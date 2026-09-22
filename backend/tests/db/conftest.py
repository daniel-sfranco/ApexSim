"""Fixtures dos testes de banco de dados.

Os testes rodam contra um PostgreSQL de verdade (o mesmo do docker-compose e
do CI), não contra mocks nem SQLite: as constraints e o comportamento de
ON DELETE são justamente o que queremos provar.

Cada suíte usa um banco descartável criado e destruído em `helpers.py`. O banco
de desenvolvimento (`apexsim`) nunca é tocado.
"""

from collections.abc import Iterator

import pytest
from alembic import command
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from db.base import criar_engine
from tests.db.helpers import alembic_config, banco_temporario


@pytest.fixture(scope="session")
def banco_migrado() -> Iterator[Engine]:
    """Engine de um banco com todas as migrations aplicadas (`upgrade head`)."""
    with banco_temporario("test") as url:
        command.upgrade(alembic_config(url), "head")
        engine = criar_engine(url)
        yield engine
        engine.dispose()


@pytest.fixture
def session(banco_migrado: Engine) -> Iterator[Session]:
    """Sessão isolada: tudo que o teste grava é desfeito ao final.

    Usa uma transação externa com SAVEPOINT, então o teste pode dar `commit()`
    ou provocar um erro de integridade sem sujar os testes seguintes.
    """
    conexao = banco_migrado.connect()
    transacao = conexao.begin()
    sessao = Session(bind=conexao, join_transaction_mode="create_savepoint")
    try:
        yield sessao
    finally:
        sessao.close()
        transacao.rollback()
        conexao.close()
