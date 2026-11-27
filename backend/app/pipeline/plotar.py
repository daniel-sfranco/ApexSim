"""Desenha os circuitos gerados para conferência visual.

O critério "plotar os pontos produz um traçado reconhecível" não se automatiza:
os testes provam as propriedades numéricas, mas quem decide se aquilo é
Interlagos é uma pessoa olhando. As imagens vão anexadas ao PR.

Uso: `docker compose run --rm api python -m app.pipeline.plotar`
"""

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from app.config import CIRCUITS_DIR  # noqa: E402


def plotar(circuit_id: str) -> None:
    dados = json.loads((CIRCUITS_DIR / f"{circuit_id}.json").read_text(encoding="utf-8"))
    pontos = dados["points"]

    x = [p["x"] for p in pontos]
    y = [p["y"] for p in pontos]

    figura, eixo = plt.subplots(figsize=(9, 9))

    # Fecha o traçado repetindo o primeiro ponto só no desenho — o arquivo
    # continua aberto, como manda o contrato.
    eixo.plot(x + x[:1], y + y[:1], linewidth=2, color="#c8102e")
    eixo.scatter(x, y, s=6, color="#1a1a1a", zorder=3)
    eixo.scatter(x[:1], y[:1], s=140, color="#0090d0", zorder=4, label="largada (distance_m = 0)")

    eixo.set_aspect("equal")
    eixo.set_title(
        f"{circuit_id} — {len(pontos)} pontos, {dados['length_m']} m\n"
        f"volta de {dados['meta']['piloto']}, "
        f"{dados['meta']['sessao']} {dados['meta']['ano']}"
    )
    eixo.legend(loc="best")
    eixo.grid(alpha=0.2)

    destino = CIRCUITS_DIR / f"{circuit_id}.png"
    figura.savefig(destino, dpi=110, bbox_inches="tight")
    plt.close(figura)
    print(f"{destino} gravado")


def main() -> None:
    for caminho in sorted(CIRCUITS_DIR.glob("*.json")):
        plotar(caminho.stem)


if __name__ == "__main__":
    main()
