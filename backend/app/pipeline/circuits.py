"""Gera os arquivos do contrato D3 a partir da telemetria do FastF1.

Executar com `make circuitos`. A saída vai para `circuits/{circuit_id}.json` e é
consumida por duas trilhas: o Daniel anota zonas por intervalo de `distance_m`
e o Anderson interpola a posição dos carros ao longo dos pontos.
"""

import json
import logging

import fastf1
import numpy as np

from app.config import (
    ANO_TELEMETRIA,
    CIRCUITOS,
    CIRCUITS_DIR,
    PONTOS_MAX,
    PONTOS_MIN,
    SESSAO_TELEMETRIA,
    Circuito,
    settings,
)
from app.pipeline import geometria
from app.pipeline.rdp import buscar_epsilon

logger = logging.getLogger(__name__)


def carregar_volta_de_referencia(circuito: Circuito):
    """Devolve a telemetria da volta mais rápida limpa do circuito.

    Descarta voltas de entrada e saída de boxes antes de escolher a mais
    rápida: uma in-lap contém o trajeto do pit lane, que não faz parte do
    traçado e deformaria a polyline.
    """
    sessao = fastf1.get_session(ANO_TELEMETRIA, circuito.rodada, SESSAO_TELEMETRIA)
    sessao.load(telemetry=True, weather=False, messages=False)

    volta = sessao.laps.pick_wo_box().pick_fastest()
    return volta, volta.get_telemetry()


def montar_circuito(circuito: Circuito) -> dict:
    """Roda o pipeline inteiro para um circuito e devolve o dicionário D3."""
    volta, telemetria = carregar_volta_de_referencia(circuito)

    pontos = geometria.converter_para_metros(
        telemetria["X"].to_numpy(dtype=float),
        telemetria["Y"].to_numpy(dtype=float),
    )
    pontos = geometria.remover_pontos_repetidos(pontos)

    epsilon, indices = buscar_epsilon(pontos, PONTOS_MIN, PONTOS_MAX)
    simplificados = pontos[indices]

    distancias, perimetro = geometria.distancias_acumuladas(simplificados)
    simplificados, distancias, k = geometria.normalizar(
        simplificados, distancias, perimetro, circuito.length_m
    )

    logger.info(
        "%s: %d pontos, epsilon=%.3f m, perímetro medido=%.1f m, k=%.4f",
        circuito.circuit_id,
        len(simplificados),
        epsilon,
        perimetro,
        k,
    )

    return {
        "circuit_id": circuito.circuit_id,
        "length_m": circuito.length_m,
        "points": [
            {"x": round(float(x), 2), "y": round(float(y), 2), "distance_m": round(float(d), 2)}
            for (x, y), d in zip(simplificados, distancias, strict=True)
        ],
        # Metadados de proveniência: sem eles o artefato não é reproduzível.
        # Não fazem parte do contrato acordado, mas são aditivos e não
        # atrapalham quem só lê circuit_id, length_m e points.
        "meta": {
            "fonte": "FastF1",
            "ano": ANO_TELEMETRIA,
            "sessao": SESSAO_TELEMETRIA,
            "piloto": str(volta["Driver"]),
            "volta": int(volta["LapNumber"]),
            "fastf1_versao": fastf1.__version__,
            "epsilon_m": round(epsilon, 4),
            "perimetro_medido_m": round(perimetro, 2),
            "fator_escala": round(k, 6),
        },
    }


def gerar(circuit_id: str) -> dict:
    """Gera e grava o JSON de um circuito."""
    circuito = CIRCUITOS[circuit_id]
    dados = montar_circuito(circuito)

    CIRCUITS_DIR.mkdir(parents=True, exist_ok=True)
    destino = CIRCUITS_DIR / f"{circuit_id}.json"
    destino.write_text(json.dumps(dados, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # O último ponto não fecha em length_m: falta o segmento que volta à linha
    # de largada, que existe na geometria mas não é um ponto da lista.
    fechamento = circuito.length_m - dados["points"][-1]["distance_m"]
    logger.info(
        "%s gravado em %s (%d pontos, segmento de fechamento %.1f m)",
        circuit_id,
        destino,
        len(dados["points"]),
        fechamento,
    )
    return dados


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    fastf1.Cache.enable_cache(str(settings.fastf1_cache_dir))
    np.seterr(all="raise")

    for circuit_id in CIRCUITOS:
        gerar(circuit_id)


if __name__ == "__main__":
    main()
