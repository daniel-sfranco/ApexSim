"""Curvas de degradação de pneu a partir das corridas de 2023 e 2024 (entrega D5).

Executar com `make dados`. Grava em `data/curvas_degradacao/`:

- `curvas_degradacao.json`: a entrega ao Isaac (curva medida + parâmetros).
- `curvas_degradacao.csv`: a mesma curva em tabela.
- `sensibilidade.csv`: quanto a curva muda se as escolhas de filtro mudarem.
- `curvas_degradacao.png`: gráfico para conferência visual.

O QUE SE MEDE
-------------
A perda de tempo por volta em função da idade do pneu, por composto. Comparar
o tempo de volta cru entre idades engana: o carro fica mais leve a cada volta
(combustível), a pista "borracha", e pilotos e circuitos têm ritmos muito
diferentes. Por isso o tempo de volta é modelado como

    tempo = base(piloto, corrida) + inclinação(corrida) * volta
            + deslocamento(composto) + degradação(composto, idade)

- `base(piloto, corrida)` remove a diferença de ritmo entre pilotos e circuitos.
- `inclinação(corrida) * volta` absorve, juntos, o combustível queimado e a
  evolução da pista, sem que seja preciso assumir um valor para nenhum dos
  dois. É identificável porque os stints começam em voltas diferentes.
- `degradação(composto, idade)` é o que interessa, estimado idade a idade (sem
  impor forma) e relativo à `IDADE_REFERENCIA`.

Só depois se ajusta a forma paramétrica do `physics.py` do Isaac à curva medida.

LIMITAÇÕES (dizer na arguição)
------------------------------
- Viés de seleção: só chega a idades altas quem escolheu ou pôde continuar com
  o pneu, então as idades altas retratam stints que estavam indo bem.
- Tráfego, gestão de pneus pelo piloto e carro à frente não são controlados.
- O erro-padrão é agrupado por corrida (44 grupos): é honesto, mas aproximado.
- O deslocamento de composto e a base mudam com a temperatura da pista, que
  não entra no modelo (o `physics.py` a trata em um termo separado).
"""

import argparse
import json
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.optimize import curve_fit, lsq_linear

from app.config import (
    COMPOSTOS_SECOS,
    CURVAS_DIR,
    IDADE_REFERENCIA,
    LIMITE_VOLTA_ANOMALA,
    MAPEAMENTOS_DIR,
    MIN_VOLTAS_POR_IDADE,
    SESSAO_CORRIDA,
)
from app.pipeline import fontes

logger = logging.getLogger(__name__)

# Diferença de BIC a partir da qual o termo de "cliff" é aceito: 10 é o limiar
# de evidência "muito forte" (Raftery, 1995). Abaixo disso o cliff não é
# distinguível de uma curva quadrática e NÃO se entrega parâmetro de cliff.
DELTA_BIC_CLIFF = 10.0

# Limites numéricos do ajuste do cliff. Não são física: só impedem o otimizador
# de divergir. Se o resultado encostar num deles, o cliff não é aceito.
CLIFF_DELTA_MAX_S = 5.0
CLIFF_BETA_MIN, CLIFF_BETA_MAX = 0.05, 5.0

# O cliff só é aceito se estiver a pelo menos esta distância (em voltas) das
# pontas da faixa observada. Um "cliff" colado no início é uma curva côncava
# imitada por uma logística lenta, e um colado no fim não tem dados depois dele.
MARGEM_DO_CLIFF_VOLTAS = 2

CHAVE_PILOTO_CORRIDA = ["Ano", "GP", "Driver"]
CHAVE_CORRIDA = ["Ano", "GP"]


# --------------------------------------------------------------------------
# Limpeza
# --------------------------------------------------------------------------


def filtrar_voltas_limpas(
    voltas: pd.DataFrame,
    limite_anomala: float = LIMITE_VOLTA_ANOMALA,
    gps_excluidos: tuple[str, ...] = (),
) -> pd.DataFrame:
    """Fica só com voltas de corrida, em pista seca, sem saída/entrada do box.

    Ordem importa: os limites de cada stint são calculados ANTES dos demais
    filtros, senão uma volta sem tempo apagaria a "primeira volta" verdadeira do
    stint e a volta seguinte seria tomada, por engano, como volta de saída.
    """
    corrida = voltas[voltas["Sessao"] == SESSAO_CORRIDA].copy()
    stint = corrida.groupby([*CHAVE_PILOTO_CORRIDA, "Stint"])["LapNumber"]
    corrida["primeira_do_stint"] = stint.transform("min")
    corrida["ultima_do_stint"] = stint.transform("max")

    limpas = corrida[
        (corrida["Chuva"] == False)  # noqa: E712 - NaN (sem leitura) deve ficar de fora
        & corrida["Compound"].isin(COMPOSTOS_SECOS)
        & ~corrida["GP"].isin(gps_excluidos)
        & (corrida["LapNumber"] > 1)
        & (corrida["LapNumber"] > corrida["primeira_do_stint"])
        & (corrida["LapNumber"] < corrida["ultima_do_stint"])
    ].dropna(subset=["LapTime", "TyreLife", "LapNumber"])

    mediana = limpas.groupby(CHAVE_PILOTO_CORRIDA)["LapTime"].transform("median")
    return limpas[limpas["LapTime"] <= limite_anomala * mediana].reset_index(drop=True)


def idade_maxima_suportada(voltas: pd.DataFrame, composto: str) -> int:
    """Maior idade, contígua desde a referência, com voltas suficientes."""
    contagem = voltas[voltas["Compound"] == composto]["TyreLife"].astype(int).value_counts()
    idade = IDADE_REFERENCIA
    while contagem.get(idade + 1, 0) >= MIN_VOLTAS_POR_IDADE:
        idade += 1
    return idade


# --------------------------------------------------------------------------
# Estimação (efeitos fixos + erro-padrão agrupado por corrida)
# --------------------------------------------------------------------------


@dataclass
class CurvaMedida:
    """Perda de tempo (s) relativa à idade de referência, por idade."""

    composto: str
    idades: np.ndarray
    delta_s: np.ndarray
    erro_padrao_s: np.ndarray
    n_voltas: np.ndarray


def estimar_curvas(voltas: pd.DataFrame) -> dict[str, CurvaMedida]:
    """Estima a curva de degradação de cada composto seco, idade a idade."""
    maximas = {c: idade_maxima_suportada(voltas, c) for c in COMPOSTOS_SECOS}
    dados = voltas[voltas["TyreLife"].astype(int) >= IDADE_REFERENCIA].copy()
    dados["idade"] = dados["TyreLife"].astype(int)
    dados = dados[dados["idade"] <= dados["Compound"].map(maximas)].reset_index(drop=True)

    n = len(dados)
    piloto_corrida = dados.groupby(CHAVE_PILOTO_CORRIDA).ngroup().to_numpy()
    corrida = dados.groupby(CHAVE_CORRIDA).ngroup().to_numpy()
    n_pc, n_corr = piloto_corrida.max() + 1, corrida.max() + 1
    linhas = np.arange(n)

    blocos = [sparse.csr_matrix((np.ones(n), (linhas, piloto_corrida)), shape=(n, n_pc))]
    # Inclinação por corrida, com a volta centrada na média da corrida para
    # não competir com o efeito fixo de piloto.
    volta = dados["LapNumber"].to_numpy(dtype=float)
    volta_centrada = volta - pd.Series(volta).groupby(corrida).transform("mean").to_numpy()
    blocos.append(sparse.csr_matrix((volta_centrada, (linhas, corrida)), shape=(n, n_corr)))

    # Deslocamento de composto (HARD é a referência; o primeiro da lista fica sem coluna).
    for composto in COMPOSTOS_SECOS[:-1]:
        blocos.append(sparse.csr_matrix((dados["Compound"] == composto).to_numpy(float)[:, None]))

    posicao: dict[tuple[str, int], int] = {}
    colunas_idade = []
    proxima = n_pc + n_corr + len(COMPOSTOS_SECOS) - 1
    for composto in COMPOSTOS_SECOS:
        do_composto = (dados["Compound"] == composto).to_numpy()
        for idade in range(IDADE_REFERENCIA + 1, maximas[composto] + 1):
            colunas_idade.append((do_composto & (dados["idade"] == idade).to_numpy()).astype(float))
            posicao[(composto, idade)] = proxima
            proxima += 1
    blocos.append(sparse.csr_matrix(np.column_stack(colunas_idade)))

    x = sparse.hstack(blocos).tocsr()
    y = dados["LapTime"].to_numpy(dtype=float)

    # Sistema normal denso (~1.000 colunas): pequeno e bem-condicionado o bastante.
    a = (x.T @ x).toarray()
    beta = np.linalg.lstsq(a, x.T @ y, rcond=None)[0]
    residuo = y - x @ beta

    # Variância agrupada por corrida (sanduíche): as voltas de uma mesma corrida
    # compartilham safety car, clima e estado da pista, então não são independentes.
    grupos = sparse.csr_matrix((np.ones(n), (corrida, linhas)), shape=(n_corr, n))
    escores = grupos @ x.multiply(residuo[:, None]).tocsr()
    escores = np.asarray(escores.todense())
    a_inv = np.linalg.pinv(a)
    variancia = a_inv @ (escores.T @ escores) @ a_inv * (n_corr / (n_corr - 1))

    curvas = {}
    for composto in COMPOSTOS_SECOS:
        idades = np.arange(IDADE_REFERENCIA, maximas[composto] + 1)
        colunas = [posicao.get((composto, i)) for i in idades]
        delta = np.array([0.0 if c is None else beta[c] for c in colunas])
        erro = np.array([0.0 if c is None else np.sqrt(max(variancia[c, c], 0.0)) for c in colunas])
        contagem = (
            dados[dados["Compound"] == composto]["idade"]
            .value_counts()
            .reindex(idades, fill_value=0)
        )
        curvas[composto] = CurvaMedida(composto, idades, delta, erro, contagem.to_numpy())
    return curvas


# --------------------------------------------------------------------------
# Ajuste da forma paramétrica do Isaac
# --------------------------------------------------------------------------


def perda_de_tempo(idade, k1_quad, k2_lin, cliff_age=0.0, cliff_delta=0.0, cliff_beta=1.0):
    """Forma do `physics.py`: quadrática + salto logístico ("cliff"), em segundos."""
    salto = cliff_delta / (1.0 + np.exp(-cliff_beta * (idade - cliff_age)))
    return k1_quad * idade**2 + k2_lin * idade + salto


def _relativa_a_referencia(idades, *parametros):
    return perda_de_tempo(idades, *parametros) - perda_de_tempo(IDADE_REFERENCIA, *parametros)


def ajustar_forma(curva: CurvaMedida) -> dict:
    """Ajusta k1, k2 e (se os dados pedirem) o cliff à curva medida.

    Devolve os parâmetros e as métricas que sustentam a decisão de aceitar ou
    não o cliff. Sem evidência, `cliff` é None: o Isaac mantém o valor estimado
    dele e sabe que o dataset não o sustenta.
    """
    mascara = curva.idades > IDADE_REFERENCIA
    idade, y, erro = curva.idades[mascara], curva.delta_s[mascara], curva.erro_padrao_s[mascara]
    erro = np.maximum(erro, 1e-3)  # evita peso infinito num ponto com erro ~ 0
    n = len(idade)

    # 1) Só a parte quadrática: linear nos parâmetros, com k1, k2 >= 0.
    colunas = np.column_stack([idade**2 - IDADE_REFERENCIA**2, idade - IDADE_REFERENCIA])
    quad = lsq_linear(colunas / erro[:, None], y / erro, bounds=(0, np.inf))
    k1, k2 = quad.x
    ajuste_quad = colunas @ quad.x
    qui2_quad = float(np.sum(((y - ajuste_quad) / erro) ** 2))
    bic_quad = qui2_quad + 2 * np.log(n)

    resultado = {
        "k1_quad": float(k1),
        "k2_lin": float(k2),
        "cliff": None,
        "qualidade": {
            # k1 colado em 0 quer dizer que a curva medida é côncava e a forma do
            # physics.py (k1 >= 0) não a captura bem; a curva medida é a referência.
            "k1_no_limite_inferior": bool(k1 < 1e-9),
            "rmse_s": float(np.sqrt(np.mean((y - ajuste_quad) ** 2))),
            "qui2_por_gl_quadratico": qui2_quad / max(n - 2, 1),
            "bic_quadratico": float(bic_quad),
            "bic_com_cliff": None,
        },
        "ajuste_s": {int(i): float(v) for i, v in zip(idade, ajuste_quad, strict=True)},
    }

    # 2) Com cliff: não-linear, várias partidas para não cair em mínimo local.
    if n < 8:
        return resultado
    idade_cliff_min = idade.min() + MARGEM_DO_CLIFF_VOLTAS
    idade_cliff_max = idade.max() - MARGEM_DO_CLIFF_VOLTAS
    if idade_cliff_min >= idade_cliff_max:
        return resultado
    limites = (
        [0, 0, idade_cliff_min, 0, CLIFF_BETA_MIN],
        [np.inf, np.inf, idade_cliff_max, CLIFF_DELTA_MAX_S, CLIFF_BETA_MAX],
    )
    melhor = None
    for idade_cliff in np.linspace(idade_cliff_min, idade_cliff_max, 6):
        for beta0 in (0.3, 1.0):
            try:
                popt, _ = curve_fit(
                    _relativa_a_referencia,
                    idade,
                    y,
                    p0=[k1, k2, idade_cliff, 0.5, beta0],
                    sigma=erro,
                    bounds=limites,
                    maxfev=20000,
                )
            except RuntimeError:
                continue
            qui2 = float(np.sum(((y - _relativa_a_referencia(idade, *popt)) / erro) ** 2))
            if melhor is None or qui2 < melhor[1]:
                melhor = (popt, qui2)
    if melhor is None:
        return resultado

    popt, qui2_cliff = melhor
    bic_cliff = qui2_cliff + 5 * np.log(n)
    resultado["qualidade"]["bic_com_cliff"] = float(bic_cliff)
    encostou = (
        popt[2] <= idade_cliff_min + 0.01
        or popt[2] >= idade_cliff_max - 0.01
        or popt[3] >= CLIFF_DELTA_MAX_S * 0.99
        or popt[4] <= CLIFF_BETA_MIN * 1.01
        or popt[4] >= CLIFF_BETA_MAX * 0.99
    )
    if bic_quad - bic_cliff >= DELTA_BIC_CLIFF and not encostou:
        resultado.update(
            k1_quad=float(popt[0]),
            k2_lin=float(popt[1]),
            cliff={
                "cliff_age": float(popt[2]),
                "cliff_delta": float(popt[3]),
                "cliff_beta": float(popt[4]),
            },
            ajuste_s={
                int(i): float(v)
                for i, v in zip(idade, _relativa_a_referencia(idade, *popt), strict=True)
            },
        )
        resultado["qualidade"]["rmse_s"] = float(
            np.sqrt(np.mean((y - _relativa_a_referencia(idade, *popt)) ** 2))
        )
    return resultado


# --------------------------------------------------------------------------
# Sensibilidade e saída
# --------------------------------------------------------------------------


def gps_divergentes(caminho: Path = MAPEAMENTOS_DIR / "sobreposicao_fontes.csv") -> tuple[str, ...]:
    """GPs em que as duas fontes discordam (numeração de volta ou composto)."""
    if not caminho.is_file():
        return ()
    tabela = pd.read_csv(caminho).iloc[:-1]  # a última linha é o TOTAL
    deslocado = pd.to_numeric(tabela["deslocamento_de_volta"], errors="coerce").fillna(0) != 0
    return tuple(tabela.loc[deslocado | (tabela["pct_composto_diverge"] > 5), "gp_nome"])


def analisar_sensibilidade(voltas: pd.DataFrame) -> pd.DataFrame:
    """Refaz a estimativa com filtros diferentes e compara a perda em idades fixas."""
    variantes = {
        "base": {},
        "limite_105": {"limite_anomala": 1.05},
        "limite_110": {"limite_anomala": 1.10},
    }
    divergentes = gps_divergentes()
    if divergentes:
        variantes["sem_gps_divergentes"] = {"gps_excluidos": divergentes}

    linhas = []
    for nome, opcoes in variantes.items():
        limpas = filtrar_voltas_limpas(voltas, **opcoes)
        for composto, curva in estimar_curvas(limpas).items():
            linha = {"variante": nome, "composto": composto, "n_voltas": int(curva.n_voltas.sum())}
            linha["idade_max"] = int(curva.idades.max())
            for idade in (10, 15):
                achou = np.where(curva.idades == idade)[0]
                linha[f"perda_idade_{idade}_s"] = (
                    round(float(curva.delta_s[achou[0]]), 3) if len(achou) else None
                )
            linhas.append(linha)
    return pd.DataFrame(linhas)


def montar_entrega(curvas: dict[str, CurvaMedida], formas: dict[str, dict], n_voltas: int) -> dict:
    """Estrutura do JSON entregue ao Isaac."""
    return {
        "meta": {
            "fonte": "vanshbatra26/f1-tyre-strategy-engine-datasets (FastF1), corridas 2023-2024",
            "unidade": "segundos de perda por volta, relativa à idade de referência",
            "idade_referencia": IDADE_REFERENCIA,
            "n_voltas_limpas": n_voltas,
            "filtros": {
                "sessao": SESSAO_CORRIDA,
                "pista": "seca",
                "compostos": list(COMPOSTOS_SECOS),
                "descartadas": "volta 1, saída e entrada do box, mais lenta que "
                f"{LIMITE_VOLTA_ANOMALA:.2f}x a mediana do piloto na corrida",
                "min_voltas_por_idade": MIN_VOLTAS_POR_IDADE,
            },
            "modelo": "tempo = base(piloto,corrida) + inclinacao(corrida)*volta "
            "+ deslocamento(composto) + degradacao(composto,idade)",
            "regra_do_cliff": f"aceito só se o BIC melhorar em >= {DELTA_BIC_CLIFF:g} "
            "e ele estiver "
            f"a >= {MARGEM_DO_CLIFF_VOLTAS} voltas das pontas da faixa observada. `cliff` null "
            "significa NÃO OBSERVADO na faixa medida (até `idade_max_suportada`), não que não "
            "exista: as equipes trocam o pneu antes de chegar lá, então os dados não alcançam.",
        },
        "compostos": {
            composto: {
                "idade_max_suportada": int(curva.idades.max()),
                "curva": [
                    {
                        "idade": int(i),
                        "perda_s": round(float(d), 4),
                        "erro_padrao_s": round(float(e), 4),
                        "n_voltas": int(k),
                    }
                    for i, d, e, k in zip(
                        curva.idades,
                        curva.delta_s,
                        curva.erro_padrao_s,
                        curva.n_voltas,
                        strict=True,
                    )
                ],
                "parametros": {
                    "k1_quad": round(formas[composto]["k1_quad"], 6),
                    "k2_lin": round(formas[composto]["k2_lin"], 6),
                    "cliff": formas[composto]["cliff"],
                },
                "qualidade": formas[composto]["qualidade"],
            }
            for composto, curva in curvas.items()
        },
    }


def gerar(saida: Path = CURVAS_DIR) -> dict:
    """Roda a estimativa inteira e grava JSON, CSVs e gráfico."""
    voltas = fontes.carregar_voltas_pneus()
    limpas = filtrar_voltas_limpas(voltas)
    curvas = estimar_curvas(limpas)
    formas = {c: ajustar_forma(curva) for c, curva in curvas.items()}
    entrega = montar_entrega(curvas, formas, len(limpas))

    saida.mkdir(parents=True, exist_ok=True)
    (saida / "curvas_degradacao.json").write_text(
        json.dumps(entrega, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    tabela = pd.DataFrame(
        [
            {"composto": c, **ponto}
            for c, dados in entrega["compostos"].items()
            for ponto in dados["curva"]
        ]
    )
    tabela.to_csv(saida / "curvas_degradacao.csv", index=False, lineterminator="\n")
    analisar_sensibilidade(voltas).to_csv(
        saida / "sensibilidade.csv", index=False, lineterminator="\n"
    )

    from app.pipeline.plotar_degradacao import desenhar

    desenhar(curvas, formas, saida / "curvas_degradacao.png")

    for composto, dados in entrega["compostos"].items():
        p = dados["parametros"]
        logger.info(
            "%-7s até %2d voltas | k1=%.5f k2=%.4f | cliff: %s",
            composto,
            dados["idade_max_suportada"],
            p["k1_quad"],
            p["k2_lin"],
            "aceito" if p["cliff"] else "não sustentado pelos dados",
        )
    return entrega


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    argparse.ArgumentParser(description=__doc__.split("\n")[0]).parse_args()
    gerar()


if __name__ == "__main__":
    main()
