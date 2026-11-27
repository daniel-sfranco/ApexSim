"""Fixtures dos testes da API: o FastAPI contra o PostgreSQL de teste, sem persistir nada."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db_sessao import obter_sessao
from app.main import app
from db.seed import carregar_referencia, popular
from tests.db.conftest import banco_migrado, session  # noqa: F401 - fixtures reaproveitadas


@pytest.fixture
def cliente(session: Session) -> Iterator[TestClient]:  # noqa: F811
    """Cliente HTTP cujas rotas usam a sessão de teste (desfeita ao final) e o seed aplicado."""
    popular(session, carregar_referencia())
    app.dependency_overrides[obter_sessao] = lambda: session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
