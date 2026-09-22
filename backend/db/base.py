"""Base declarativa do SQLAlchemy e conexão com o PostgreSQL."""

from sqlalchemy import MetaData
from sqlalchemy.engine import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# Nomes determinísticos para constraints e índices. Sem isto o PostgreSQL
# inventa nomes (ex.: "lap_records_check1") que variam entre bancos, e o
# Alembic não consegue dropar ou alterar a constraint de forma reprodutível.
CONVENCAO_DE_NOMES = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Classe-mãe de todos os modelos ORM do ApexSim."""

    metadata = MetaData(naming_convention=CONVENCAO_DE_NOMES)


def sqlalchemy_url(url: str | None = None) -> str:
    """Devolve a URL do banco no formato que o SQLAlchemy entende.

    O docker-compose (e o resto do time) usa `postgresql://...`. Para o
    SQLAlchemy isso significa o driver antigo psycopg2, que não instalamos, então
    trocamos o esquema para `postgresql+psycopg://` (psycopg 3) aqui, em um único
    lugar, em vez de mudar a variável DATABASE_URL que outras trilhas já usam.
    """
    url = url or settings.database_url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def criar_engine(url: str | None = None) -> Engine:
    """Cria um engine SQLAlchemy apontando para o PostgreSQL do projeto."""
    return create_engine(sqlalchemy_url(url), pool_pre_ping=True)
