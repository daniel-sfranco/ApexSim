"""Popula as tabelas de referência do banco a partir dos mapeamentos versionados.

Executar com `make seed`. Lê `data/mapeamentos/` (gerado por `make dados`) e a
lista de circuitos do projeto em `app.config`:

- `tyre_compounds`: os compostos mapeados (os "desconhecidos" ficam de fora).
- `circuits`: só os circuitos do ApexSim, com o comprimento oficial.
- `drivers` e `teams`: o grid de uma temporada (`TEMPORADA_DO_SEED`).

É idempotente: rodar duas vezes não duplica nada, e rodar depois de mudar um CSV
corrige as linhas que mudaram. Nunca apaga linhas. A sincronização é por chave
natural (código, slug, nome) em vez de `ON CONFLICT`, porque cada conflito
gastaria um id da sequência a cada execução.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import COMPOSTOS_SEM_DADO_NO_BANCO, MAPEAMENTOS_DIR, TEMPORADA_DO_SEED
from db.base import Base, criar_engine
from db.models import Circuit, Driver, Team, TyreCompound

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Referencia:
    """Linhas de referência prontas para gravar, uma lista por tabela."""

    compostos: list[dict[str, Any]]
    circuitos: list[dict[str, Any]]
    pilotos: list[dict[str, Any]]
    equipes: list[dict[str, Any]]


def carregar_referencia(
    pasta: Path = MAPEAMENTOS_DIR, temporada: int = TEMPORADA_DO_SEED
) -> Referencia:
    """Lê os CSVs de mapeamento e monta as linhas de cada tabela."""
    compostos = pd.read_csv(pasta / "compostos.csv", keep_default_na=False)
    circuitos = pd.read_csv(pasta / "circuitos.csv", keep_default_na=False)
    pilotos = pd.read_csv(pasta / "pilotos.csv", keep_default_na=False)
    equipes = pd.read_csv(pasta / "equipes.csv", keep_default_na=False)

    compostos = compostos[compostos["acao"] == "mapeado"].drop_duplicates("codigo_banco")
    circuitos = circuitos[circuitos["no_projeto"].astype(str) == "True"]
    pilotos = pilotos[pilotos["temporada"] == temporada]
    equipes = equipes[equipes["temporada"] == temporada]
    if pilotos.empty or equipes.empty:
        raise ValueError(f"Nenhum piloto ou equipe de {temporada} em {pasta}. Rode `make dados`.")

    return Referencia(
        compostos=[
            *({"code": r.codigo_banco, "name_pt": r.nome_pt} for r in compostos.itertuples()),
            *({"code": c, "name_pt": nome} for c, nome in COMPOSTOS_SEM_DADO_NO_BANCO.items()),
        ],
        circuitos=[
            {
                "id": r.circuit_id,
                "name": r.nome_circuito,
                "country": r.pais,
                "length_m": int(r.length_m_oficial),
            }
            for r in circuitos.itertuples()
        ],
        pilotos=[
            {"code": r.codigo, "full_name": r.nome_completo, "equipe": r.equipe or None}
            for r in pilotos.itertuples()
        ],
        equipes=[{"name": r.equipe} for r in equipes.itertuples()],
    )


def _sincronizar(
    session: Session, modelo: type[Base], chave: str, linhas: list[dict[str, Any]]
) -> dict[str, int]:
    """Cria o que falta e corrige o que mudou, casando pela chave natural."""
    existentes = {getattr(o, chave): o for o in session.scalars(select(modelo))}
    contagem = {"criados": 0, "atualizados": 0, "inalterados": 0}
    for linha in linhas:
        atual = existentes.get(linha[chave])
        if atual is None:
            session.add(modelo(**linha))
            contagem["criados"] += 1
        elif any(getattr(atual, campo) != valor for campo, valor in linha.items()):
            for campo, valor in linha.items():
                setattr(atual, campo, valor)
            contagem["atualizados"] += 1
        else:
            contagem["inalterados"] += 1
    session.flush()
    return contagem


def popular(session: Session, referencia: Referencia) -> dict[str, dict[str, int]]:
    """Grava a referência. Não dá commit: quem chama decide (o teste desfaz)."""
    resumo = {
        "tyre_compounds": _sincronizar(session, TyreCompound, "code", referencia.compostos),
        "circuits": _sincronizar(session, Circuit, "id", referencia.circuitos),
        "teams": _sincronizar(session, Team, "name", referencia.equipes),
    }
    # Os pilotos dependem das equipes já gravadas: a equipe padrão vira o `team_id`.
    id_da_equipe = {nome: id_ for nome, id_ in session.execute(select(Team.name, Team.id))}
    pilotos = []
    for p in referencia.pilotos:
        equipe = p["equipe"]
        if equipe is not None and equipe not in id_da_equipe:
            raise ValueError(f"equipe {equipe!r} do piloto {p['code']} não está em equipes.csv")
        pilotos.append(
            {"code": p["code"], "full_name": p["full_name"], "team_id": id_da_equipe.get(equipe)}
        )
    resumo["drivers"] = _sincronizar(session, Driver, "code", pilotos)
    return resumo


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    engine = criar_engine()
    with Session(engine) as session:
        resumo = popular(session, carregar_referencia())
        session.commit()
    for tabela, contagem in resumo.items():
        logger.info("%-15s %s", tabela, contagem)
    engine.dispose()


if __name__ == "__main__":
    main()
