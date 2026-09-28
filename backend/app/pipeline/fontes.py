"""Leitura dos datasets brutos do Kaggle, com os nomes de coluna unificados.

Centraliza o que é específico de cada fonte (nomes de arquivo, `\\N` do Ergast,
coluna de sessão que se chama `Session` em 2023 e `SessionType` em 2024) para
que a reconciliação e o ajuste da degradação não repitam essa lógica.
"""

from pathlib import Path

import pandas as pd

from app.config import (
    PASTA_HISTORICO,
    PASTA_PNEUS,
    PASTA_VOLTAS_ALEXJR,
    TEMPORADAS_PNEUS,
)

# Colunas do dataset de pneus que o projeto usa. Ler só estas evita carregar
# 26 colunas de telemetria e clima de que ninguém precisa.
COLUNAS_PNEUS = [
    "GP",
    "Driver",
    "Stint",
    "LapNumber",
    "Compound",
    "TyreLife",
    "LapTime",
    "Rainfall",
    "Session",
    "SessionType",
]

# Em 2023 a sessão está em `Session`; em 2024, em `SessionType`.
_ARQUIVO_PNEUS = "{ano}/final_merged_{ano}_data.csv"

_BOOLEANOS = {True: True, False: False, "True": True, "False": False}


def carregar_voltas_pneus(
    pasta: Path = PASTA_PNEUS, temporadas: tuple[int, ...] = TEMPORADAS_PNEUS
) -> pd.DataFrame:
    """Voltas do dataset de pneus (`vanshbatra26`), todas as sessões, 2023 e 2024.

    Colunas: Ano, Sessao, GP, Driver, Stint, LapNumber, Compound, TyreLife,
    LapTime, Chuva. `Sessao` é NaN nas linhas em que o dataset não a informa
    (2.155 linhas do GP de Abu Dhabi de 2023); elas nunca são tratadas como
    corrida.
    """
    quadros = []
    for ano in temporadas:
        caminho = pasta / _ARQUIVO_PNEUS.format(ano=ano)
        bruto = pd.read_csv(caminho, low_memory=False)
        colunas = [c for c in COLUNAS_PNEUS if c in bruto.columns]
        df = bruto[colunas].copy()
        df["Sessao"] = df["Session"] if "Session" in df else df["SessionType"]
        df = df.drop(columns=[c for c in ("Session", "SessionType") if c in df])
        df["Ano"] = ano
        # `Rainfall` vem como texto misto; NaN (sem leitura de clima) fica NaN.
        df["Chuva"] = df.pop("Rainfall").map(_BOOLEANOS)
        quadros.append(df)
    return pd.concat(quadros, ignore_index=True)


def carregar_voltas_alexjr(pasta: Path = PASTA_VOLTAS_ALEXJR) -> pd.DataFrame:
    """Voltas do dataset `alexjr2001`, um arquivo por GP, todas na temporada 2024.

    O nome do arquivo usa `_` no lugar de espaço (`Sao_Paulo_Grand_Prix`); aqui
    ele é convertido para o nome do GP usado nas outras fontes.
    """
    quadros = []
    for caminho in sorted(pasta.glob("*.csv")):
        df = pd.read_csv(
            caminho, usecols=["Driver", "LapNumber", "Compound", "TyreLife", "LapTime"]
        )
        df["GP"] = caminho.stem.replace("_", " ")
        quadros.append(df)
    voltas = pd.concat(quadros, ignore_index=True)
    voltas["LapNumber"] = voltas["LapNumber"].astype(int)
    return voltas


def carregar_historico(pasta: Path = PASTA_HISTORICO) -> dict[str, pd.DataFrame]:
    """Tabelas do dataset histórico (`jtrotman`, derivado do Ergast) que interessam.

    O Ergast escreve `\\N` para "sem valor"; aqui isso vira NaN. É o caso de
    757 dos 865 pilotos, que não têm código de três letras.
    """
    return {
        "races": pd.read_csv(pasta / "races.csv", usecols=["raceId", "year", "circuitId", "name"]),
        "circuits": pd.read_csv(
            pasta / "circuits.csv", usecols=["circuitId", "circuitRef", "name", "country"]
        ),
        "drivers": pd.read_csv(
            pasta / "drivers.csv",
            usecols=["driverId", "driverRef", "code", "forename", "surname"],
            na_values=["\\N"],
        ),
        "results": pd.read_csv(pasta / "results.csv", usecols=["raceId", "driverId"]),
    }
