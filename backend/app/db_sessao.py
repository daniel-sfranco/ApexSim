"""Sessão do banco para as rotas da API (dependência do FastAPI)."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from db.base import criar_engine


@lru_cache(maxsize=1)
def engine() -> Engine:
    """Um engine por processo, criado na primeira requisição (e não ao importar o módulo)."""
    return criar_engine()


def obter_sessao() -> Iterator[Session]:
    """Abre uma sessão por requisição: confirma se a rota terminou bem, desfaz se falhou.

    Os testes substituem esta dependência (`app.dependency_overrides`) por uma sessão que
    nunca persiste.
    """
    with Session(engine()) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
