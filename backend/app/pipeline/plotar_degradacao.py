"""Gráfico das curvas de degradação medidas, para conferência visual.

Cores: os três primeiros slots da paleta categórica validada (azul, laranja,
água-marinha), em ordem fixa por composto do mais macio ao mais duro. As cores
oficiais da Pirelli (vermelho, amarelo, branco) ficaram de fora de propósito:
o branco não tem contraste sobre fundo claro. O verde-água tem contraste 2,7:1
com o fundo, então cada curva também recebe rótulo direto e a mesma tabela sai
em `curvas_degradacao.csv`.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # sem tela: roda dentro do contêiner
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

from app.config import IDADE_REFERENCIA, PARAMETROS_ISAAC_ESTIMADOS  # noqa: E402

SUPERFICIE = "#fcfcfb"
TINTA = "#0b0b0b"
TINTA_SECUNDARIA = "#52514e"
GRADE = "#e6e5e1"
ESTIMADO = "#8a8984"
COR_DO_COMPOSTO = {"SOFT": "#2a78d6", "MEDIUM": "#eb6834", "HARD": "#1baf7a"}
NOME_DO_COMPOSTO = {"SOFT": "Macio", "MEDIUM": "Médio", "HARD": "Duro"}


def _estimado_do_isaac(composto: str, idades: np.ndarray) -> np.ndarray:
    """Curva do `physics.py` (palpite, não medição), relativa à idade de referência."""
    from app.pipeline.degradacao import perda_de_tempo

    p = PARAMETROS_ISAAC_ESTIMADOS[composto]
    return perda_de_tempo(idades, **p) - perda_de_tempo(IDADE_REFERENCIA, **p)


def desenhar(curvas, formas, destino: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 5.4), dpi=150, facecolor=SUPERFICIE)
    ax.set_facecolor(SUPERFICIE)

    for composto, curva in curvas.items():
        cor = COR_DO_COMPOSTO[composto]
        ax.fill_between(
            curva.idades,
            curva.delta_s - 1.96 * curva.erro_padrao_s,
            curva.delta_s + 1.96 * curva.erro_padrao_s,
            color=cor,
            alpha=0.12,
            linewidth=0,
        )
        ax.plot(
            curva.idades,
            curva.delta_s,
            "o",
            color=cor,
            markersize=4.5,
            markeredgecolor=SUPERFICIE,
            markeredgewidth=1,
        )
        ajuste = formas[composto]["ajuste_s"]
        ax.plot(list(ajuste), list(ajuste.values()), "-", color=cor, linewidth=2)
        ax.plot(
            curva.idades,
            _estimado_do_isaac(composto, curva.idades),
            "--",
            color=ESTIMADO,
            linewidth=1.2,
        )
        # Rótulo direto na ponta da curva, em tinta (nunca na cor da série).
        ax.annotate(
            f"{NOME_DO_COMPOSTO[composto]} ({composto.title()})",
            (curva.idades[-1], curva.delta_s[-1]),
            xytext=(6, 0),
            textcoords="offset points",
            va="center",
            fontsize=9,
            color=TINTA,
        )

    ax.set_xlabel("Idade do pneu (voltas)", color=TINTA_SECUNDARIA, fontsize=10)
    ax.set_ylabel(
        f"Perda de tempo por volta vs. idade {IDADE_REFERENCIA} (s)",
        color=TINTA_SECUNDARIA,
        fontsize=10,
    )
    ax.set_title(
        "Degradação de pneu medida em corridas de 2023-2024",
        loc="left",
        color=TINTA,
        fontsize=13,
        fontweight="bold",
        pad=22,
    )
    ax.text(
        0,
        1.02,
        "Pontos: estimativa por idade, faixa: IC 95% | linha: forma do physics.py ajustada | "
        "tracejado cinza: estimativa atual do physics.py",
        transform=ax.transAxes,
        fontsize=8,
        color=TINTA_SECUNDARIA,
    )
    ax.grid(axis="y", color=GRADE, linewidth=0.8)
    ax.set_axisbelow(True)
    for lado in ("top", "right", "left"):
        ax.spines[lado].set_visible(False)
    ax.spines["bottom"].set_color(GRADE)
    ax.tick_params(colors=TINTA_SECUNDARIA, length=0)
    ax.set_xlim(0, max(c.idades.max() for c in curvas.values()) + 9)
    legenda = [
        Line2D(
            [],
            [],
            color=COR_DO_COMPOSTO[c],
            marker="o",
            markersize=4.5,
            linewidth=2,
            markeredgecolor=SUPERFICIE,
            label=f"{NOME_DO_COMPOSTO[c]} ({c.title()})",
        )
        for c in curvas
    ] + [
        Line2D(
            [],
            [],
            color=ESTIMADO,
            linestyle="--",
            linewidth=1.2,
            label="Estimativa atual do physics.py",
        )
    ]
    ax.legend(
        handles=legenda,
        loc="upper left",
        frameon=False,
        fontsize=9,
        labelcolor=TINTA_SECUNDARIA,
    )
    fig.tight_layout()
    fig.savefig(destino, facecolor=SUPERFICIE)
    plt.close(fig)
