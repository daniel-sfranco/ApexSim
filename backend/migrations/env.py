"""Ambiente de execução das migrations do Alembic."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import create_engine

from db import models  # noqa: F401  (registra todos os modelos em Base.metadata)
from db.base import Base, sqlalchemy_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _url() -> str:
    """URL do banco: a definida programaticamente (testes) ou a do ambiente."""
    return config.get_main_option("sqlalchemy.url") or sqlalchemy_url()


def run_migrations_offline() -> None:
    """Gera o SQL das migrations sem conectar ao banco (`alembic upgrade --sql`)."""
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Aplica as migrations conectando ao banco."""
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Detecta mudança de tipo de coluna no autogenerate.
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
