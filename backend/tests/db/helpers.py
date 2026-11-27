"""Utilitários compartilhados pelos testes de banco (bancos descartáveis e Alembic)."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from db.base import criar_engine, sqlalchemy_url

BACKEND_DIR = Path(__file__).resolve().parents[2]


@contextmanager
def banco_temporario(sufixo: str) -> Iterator[str]:
    """Cria o banco `<nome>_<sufixo>` vazio, devolve a URL e o apaga no fim."""
    base = make_url(sqlalchemy_url())
    nome = f"{base.database}_{sufixo}"

    # Conecta no banco de manutenção "postgres" para poder criar/apagar outros.
    admin = criar_engine(base.set(database="postgres").render_as_string(hide_password=False))
    try:
        with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            quoted = admin.dialect.identifier_preparer.quote(nome)
            conn.execute(text(f"DROP DATABASE IF EXISTS {quoted} WITH (FORCE)"))
            conn.execute(text(f"CREATE DATABASE {quoted}"))
    except OperationalError as erro:
        admin.dispose()
        pytest.fail(
            "PostgreSQL inacessível para os testes de banco. Rode pelo Docker "
            "(`make test`) ou defina DATABASE_URL apontando para um Postgres "
            f"acessível.\nDetalhe: {erro.orig}",
            pytrace=False,
        )

    try:
        yield base.set(database=nome).render_as_string(hide_password=False)
    finally:
        with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text(f"DROP DATABASE IF EXISTS {quoted} WITH (FORCE)"))
        admin.dispose()


def alembic_config(url: str) -> Config:
    """Config do Alembic apontando para o banco de teste, sem depender do cwd."""
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    # O configparser trata "%" como interpolação; senhas com "%" precisam de escape.
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg
