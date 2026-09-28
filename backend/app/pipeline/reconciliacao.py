"""Reconcilia GPs, pilotos e compostos entre as três fontes do Kaggle.

Executar com `make dados`. Grava em `data/mapeamentos/` (versionado) as tabelas
que dizem, para cada nome que aparece numa fonte, a qual entidade do banco ele
corresponde:

- `circuitos.csv`: nome do GP em cada fonte -> slug do circuito (`interlagos`).
- `pilotos.csv`: (temporada, código de 3 letras) -> piloto do histórico.
- `compostos.csv`: composto de cada fonte -> código do banco (ou descarte).
- `equipes.csv`: equipes de cada temporada, com os pilotos que correram por elas.
- `sobreposicao_fontes.csv`: quanto do `alexjr2001` já está no dataset de pneus.

Por que a chave do piloto é (temporada, código) e não só o código: o código FIA
se repete no histórico (Michael e Mick Schumacher são `MSC`; Albon e Albers,
`ALB`; Max Verstappen e Vergne, `VER`). Dentro de uma temporada ele é único.
"""

import logging
from pathlib import Path

import pandas as pd

from app.config import (
    CIRCUITOS,
    COMPOSTOS_FONTE_PARA_BANCO,
    COMPOSTOS_NOME_PT,
    MAPEAMENTOS_DIR,
    SESSAO_CORRIDA,
    TEMPORADAS_PNEUS,
)
from app.pipeline import fontes

logger = logging.getLogger(__name__)

# Diferença de tempo de volta abaixo da qual duas fontes "concordam". Os
# tempos vêm do mesmo relógio do FastF1, com precisão de milissegundo.
TOLERANCIA_TEMPO_S = 0.001


class ReconciliacaoInconsistente(ValueError):
    """Uma fonte trouxe um nome que o mapeamento não sabe traduzir."""


def mapear_circuitos(
    historico: dict[str, pd.DataFrame], gps_pneus: set[str], gps_alexjr: set[str]
) -> pd.DataFrame:
    """Uma linha por GP, ligando o nome usado nas fontes ao slug do circuito."""
    corridas = historico["races"]
    corridas = corridas[corridas["year"].isin(TEMPORADAS_PNEUS)]

    presentes = gps_pneus | gps_alexjr
    sem_historico = presentes - set(corridas["name"])
    if sem_historico:
        raise ReconciliacaoInconsistente(
            f"GPs sem correspondência no histórico (races.csv): {sorted(sem_historico)}"
        )

    por_gp = (
        corridas[corridas["name"].isin(presentes)]
        .groupby("name")
        .agg(
            circuitId=("circuitId", "first"),
            n_circuitos=("circuitId", "nunique"),
            temporadas=("year", lambda s: ";".join(str(a) for a in sorted(set(s)))),
        )
        .reset_index()
    )
    if (por_gp["n_circuitos"] > 1).any():
        raise ReconciliacaoInconsistente("Um mesmo GP mudou de circuito entre as temporadas.")

    tabela = por_gp.merge(historico["circuits"], on="circuitId", suffixes=("_gp", "_circuito"))
    tabela = tabela.rename(
        columns={
            "circuitRef": "circuit_id",
            "name_gp": "gp_nome",
            "name_circuito": "nome_circuito",
            "country": "pais",
            "circuitId": "circuitId_historico",
        }
    )
    tabela["arquivo_alexjr"] = tabela["gp_nome"].map(
        lambda gp: gp.replace(" ", "_") + ".csv" if gp in gps_alexjr else ""
    )
    tabela["no_projeto"] = tabela["circuit_id"].isin(CIRCUITOS)
    tabela["length_m_oficial"] = tabela["circuit_id"].map(
        lambda c: CIRCUITOS[c].length_m if c in CIRCUITOS else pd.NA
    )
    colunas = [
        "circuit_id",
        "gp_nome",
        "nome_circuito",
        "pais",
        "temporadas",
        "arquivo_alexjr",
        "circuitId_historico",
        "no_projeto",
        "length_m_oficial",
    ]
    return tabela[colunas].sort_values("circuit_id").reset_index(drop=True)


def mapear_pilotos(
    historico: dict[str, pd.DataFrame], participantes: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Liga (temporada, código) ao piloto do histórico.

    `participantes` tem as colunas Ano, codigo e fontes. Devolve a tabela de
    mapeamento e as linhas que não acharam correspondência (para o resumo).
    """
    pilotos = historico["drivers"]
    corridas = historico["races"][["raceId", "year"]]
    correu = (
        historico["results"]
        .merge(corridas, on="raceId")
        .loc[lambda d: d["year"].isin(TEMPORADAS_PNEUS)]
        .drop_duplicates(["year", "driverId"])
        .merge(pilotos, on="driverId")
        .rename(columns={"year": "Ano", "code": "codigo"})
    )

    ambiguos = correu.groupby(["Ano", "codigo"])["driverId"].nunique()
    if (ambiguos > 1).any():
        raise ReconciliacaoInconsistente(
            f"Código repetido dentro da mesma temporada: {ambiguos[ambiguos > 1].index.tolist()}"
        )

    junto = participantes.merge(
        correu[["Ano", "codigo", "driverId", "driverRef", "forename", "surname"]],
        on=["Ano", "codigo"],
        how="left",
    )
    sem_correspondencia = junto[junto["driverId"].isna()]
    mapeados = junto.dropna(subset=["driverId"]).copy()
    mapeados["driverId"] = mapeados["driverId"].astype(int)

    # Outros pilotos do histórico que dividem o mesmo código: é o aviso de que
    # `codigo` sozinho não identifica ninguém.
    mesmos_codigos = pilotos.dropna(subset=["code"]).groupby("code")["driverRef"].apply(list)
    mapeados["codigo_repetido_com"] = [
        ";".join(sorted(set(mesmos_codigos.get(cod, [])) - {ref}))
        for cod, ref in zip(mapeados["codigo"], mapeados["driverRef"], strict=True)
    ]
    mapeados["nome_completo"] = mapeados["forename"] + " " + mapeados["surname"]
    tabela = mapeados.rename(columns={"driverId": "driverId_historico", "Ano": "temporada"})[
        [
            "temporada",
            "codigo",
            "driverId_historico",
            "driverRef",
            "nome_completo",
            "codigo_repetido_com",
            "fontes",
        ]
    ]
    return tabela.sort_values(["temporada", "codigo"]).reset_index(drop=True), sem_correspondencia


def mapear_equipes(pneus: pd.DataFrame) -> pd.DataFrame:
    """Equipes que largaram alguma corrida, por temporada, com os pilotos de cada uma.

    O nome é o do FastF1 ("Haas F1 Team", "RB"). Ele muda entre temporadas
    (Alfa Romeo virou Kick Sauber, AlphaTauri virou RB) e esta tabela NÃO tenta
    ligar as duas pontas: o seed só usa uma temporada, então não há o que
    reconciliar ainda.
    """
    corrida = pneus[(pneus["Sessao"] == SESSAO_CORRIDA)].dropna(subset=["Team"])
    tabela = (
        corrida.groupby(["Ano", "Team"])
        .agg(pilotos=("Driver", lambda s: ";".join(sorted(set(s)))), n_voltas=("Driver", "size"))
        .reset_index()
        .rename(columns={"Ano": "temporada", "Team": "equipe"})
    )
    return tabela.sort_values(["temporada", "equipe"]).reset_index(drop=True)


def mapear_compostos(observados: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por valor de composto visto nas fontes, com a ação a tomar.

    `observados` tem as colunas fonte, Compound e n_voltas.
    """
    desconhecidos = set(observados["Compound"].dropna()) - set(COMPOSTOS_FONTE_PARA_BANCO)
    if desconhecidos:
        raise ReconciliacaoInconsistente(
            f"Composto sem regra em COMPOSTOS_FONTE_PARA_BANCO: {sorted(desconhecidos)}"
        )

    linhas = []
    for valor, grupo in observados.groupby("Compound"):
        codigo = COMPOSTOS_FONTE_PARA_BANCO[valor]
        linhas.append(
            {
                "valor_fonte": valor,
                "codigo_banco": codigo or "",
                "chave_fisica": codigo.lower() if codigo else "",
                "nome_pt": COMPOSTOS_NOME_PT.get(codigo, ""),
                "acao": "mapeado" if codigo else "descartado",
                "fontes": ";".join(sorted(grupo["fonte"].unique())),
                "n_voltas": int(grupo["n_voltas"].sum()),
            }
        )
    return pd.DataFrame(linhas).sort_values("valor_fonte").reset_index(drop=True)


# Deslocamentos de numeração de volta testados entre as duas fontes. Em Mônaco
# 2024 (bandeira vermelha na largada) as duas contam as voltas com 1 de
# diferença; o `TyreLife` da mesma volta é igual nas duas, então o efeito na
# degradação é nulo, mas a divergência precisa ficar registrada.
DESLOCAMENTOS_TESTADOS = (0, -1, 1)
_CHAVE_VOLTA = ["GP", "Driver", "LapNumber"]


def _comparar_com_deslocamento(
    corrida: pd.DataFrame, alexjr: pd.DataFrame, deslocamento: int
) -> pd.DataFrame:
    """Casa cada volta do `alexjr2001` com a do dataset de pneus, GP a GP.

    `deslocamento` é somado ao número da volta do `alexjr2001` antes do casamento.
    """
    deslocado = alexjr.assign(LapNumber=alexjr["LapNumber"] + deslocamento)
    junto = deslocado.merge(
        corrida, on=_CHAVE_VOLTA, how="left", suffixes=("_alexjr", "_pneus"), indicator=True
    )
    junto["achou"] = junto["_merge"] == "both"
    diferenca = (junto["LapTime_alexjr"] - junto["LapTime_pneus"]).abs()
    junto["tempo_igual"] = junto["achou"] & (diferenca <= TOLERANCIA_TEMPO_S)
    junto["composto_igual"] = junto["achou"] & (junto["Compound_alexjr"] == junto["Compound_pneus"])
    return junto.groupby("GP").agg(
        voltas_alexjr=("achou", "size"),
        achadas_em_pneus=("achou", "sum"),
        tempo_igual=("tempo_igual", "sum"),
        composto_igual=("composto_igual", "sum"),
    )


def verificar_sobreposicao(pneus: pd.DataFrame, alexjr: pd.DataFrame) -> pd.DataFrame:
    """Compara, GP a GP, o `alexjr2001` com a corrida de 2024 do dataset de pneus.

    Responde à pergunta "esse dataset traz voltas que os outros não têm?". Para
    cada GP escolhe o deslocamento de numeração que mais voltas alinha.
    """
    corrida_2024 = pneus[(pneus["Ano"] == 2024) & (pneus["Sessao"] == SESSAO_CORRIDA)]
    if corrida_2024.duplicated(_CHAVE_VOLTA).any() or alexjr.duplicated(_CHAVE_VOLTA).any():
        raise ReconciliacaoInconsistente("Voltas duplicadas: a chave GP+piloto+volta não é única.")

    corrida = corrida_2024[[*_CHAVE_VOLTA, "LapTime", "Compound"]]
    por_deslocamento = {
        d: _comparar_com_deslocamento(corrida, alexjr, d) for d in DESLOCAMENTOS_TESTADOS
    }
    sem_deslocamento = por_deslocamento[0]["tempo_igual"]
    linhas = []
    for gp in sem_deslocamento.index:
        # `max` devolve o primeiro empate, e 0 vem primeiro: sem ganho, fica sem deslocamento.
        melhor = max(
            DESLOCAMENTOS_TESTADOS, key=lambda d: por_deslocamento[d].loc[gp, "tempo_igual"]
        )
        linha = por_deslocamento[melhor].loc[gp].to_dict()
        linhas.append(
            {
                "gp_nome": gp,
                "deslocamento_de_volta": melhor,
                **linha,
                "tempo_igual_sem_deslocamento": int(sem_deslocamento[gp]),
            }
        )
    resultado = pd.DataFrame(linhas)

    contagens = [
        "voltas_alexjr",
        "achadas_em_pneus",
        "tempo_igual",
        "composto_igual",
        "tempo_igual_sem_deslocamento",
    ]
    total = {"gp_nome": "TOTAL", "deslocamento_de_volta": ""}
    total.update({c: int(resultado[c].sum()) for c in contagens})
    resultado = pd.concat([resultado, pd.DataFrame([total])], ignore_index=True)
    resultado[contagens] = resultado[contagens].astype(int)
    resultado["pct_tempo_igual"] = (
        100 * resultado["tempo_igual"] / resultado["voltas_alexjr"]
    ).round(2)
    # Entre as voltas achadas, quantas discordam no composto: é o que pode contaminar a curva.
    resultado["pct_composto_diverge"] = (
        100
        * (resultado["achadas_em_pneus"] - resultado["composto_igual"])
        / resultado["achadas_em_pneus"]
    ).round(2)
    return resultado


def _participantes(pneus: pd.DataFrame, alexjr: pd.DataFrame) -> pd.DataFrame:
    """Pilotos que largaram alguma corrida, por temporada e fonte."""
    de_pneus = pneus[pneus["Sessao"] == SESSAO_CORRIDA][["Ano", "Driver"]].drop_duplicates()
    de_pneus["fonte"] = "pneus"
    de_alexjr = alexjr[["Driver"]].drop_duplicates()
    de_alexjr["Ano"] = 2024
    de_alexjr["fonte"] = "alexjr"
    todos = pd.concat([de_pneus, de_alexjr]).rename(columns={"Driver": "codigo"})
    return (
        todos.groupby(["Ano", "codigo"])["fonte"]
        .agg(lambda s: ";".join(sorted(set(s))))
        .rename("fontes")
        .reset_index()
    )


def gerar(saida: Path = MAPEAMENTOS_DIR) -> dict[str, int]:
    """Roda a reconciliação inteira e grava os CSVs. Devolve os números do resumo."""
    historico = fontes.carregar_historico()
    pneus = fontes.carregar_voltas_pneus()
    alexjr = fontes.carregar_voltas_alexjr()

    circuitos = mapear_circuitos(historico, set(pneus["GP"]), set(alexjr["GP"]))

    participantes = _participantes(pneus, alexjr)
    pilotos, sem_correspondencia = mapear_pilotos(historico, participantes)
    if len(sem_correspondencia):
        raise ReconciliacaoInconsistente(
            "Pilotos que correram mas não estão no histórico:\n"
            + sem_correspondencia[["Ano", "codigo"]].to_string(index=False)
        )
    so_treino = set(zip(pneus["Ano"], pneus["Driver"], strict=True)) - set(
        zip(participantes["Ano"], participantes["codigo"], strict=True)
    )

    observados = pd.concat(
        [
            pneus.groupby("Compound").size().rename("n_voltas").reset_index().assign(fonte="pneus"),
            alexjr.groupby("Compound")
            .size()
            .rename("n_voltas")
            .reset_index()
            .assign(fonte="alexjr"),
        ]
    )
    compostos = mapear_compostos(observados)
    equipes = mapear_equipes(pneus)
    sobreposicao = verificar_sobreposicao(pneus, alexjr)

    saida.mkdir(parents=True, exist_ok=True)
    for nome, tabela in (
        ("circuitos", circuitos),
        ("pilotos", pilotos),
        ("compostos", compostos),
        ("equipes", equipes),
        ("sobreposicao_fontes", sobreposicao),
    ):
        tabela.to_csv(saida / f"{nome}.csv", index=False, lineterminator="\n")

    total = sobreposicao.iloc[-1]
    resumo = {
        "circuitos": len(circuitos),
        "circuitos_no_projeto": int(circuitos["no_projeto"].sum()),
        "equipes": len(equipes),
        "pilotos_mapeados": len(pilotos),
        "pilotos_com_codigo_repetido_no_historico": int(
            (pilotos["codigo_repetido_com"] != "").sum()
        ),
        "pilotos_so_em_treino_ignorados": len(so_treino),
        "compostos_descartados": int((compostos["acao"] == "descartado").sum()),
        "voltas_alexjr": int(total["voltas_alexjr"]),
        "voltas_alexjr_ja_no_dataset_de_pneus": int(total["achadas_em_pneus"]),
        "voltas_alexjr_com_mesmo_tempo": int(total["tempo_igual"]),
        "gps_com_numeracao_de_volta_deslocada": int(
            pd.to_numeric(sobreposicao["deslocamento_de_volta"], errors="coerce")
            .fillna(0)
            .ne(0)
            .sum()
        ),
        "gps_com_divergencia_de_composto_acima_de_5pct": int(
            (sobreposicao.iloc[:-1]["pct_composto_diverge"] > 5).sum()
        ),
    }
    for chave, valor in resumo.items():
        logger.info("%-45s %s", chave, valor)
    return resumo


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    gerar()


if __name__ == "__main__":
    main()
