"""Testes da geometria e do contrato D3.

Os testes do contrato rodam sobre os JSONs já gerados em `circuits/`, nunca
contra a rede: a API do FastF1 tem rate limit baixo e derrubaria o CI.
"""

import json
import math

import numpy as np
import pytest

from app.config import CIRCUITOS, CIRCUITS_DIR, PONTOS_MAX, PONTOS_MIN
from app.pipeline import geometria

# --------------------------------------------------------------------------
# Unidades e limpeza
# --------------------------------------------------------------------------


def test_converte_decimos_de_metro_para_metros():
    pontos = geometria.converter_para_metros(np.array([100.0]), np.array([250.0]))
    assert pontos.tolist() == [[10.0, 25.0]]


def test_remove_amostras_paradas_mas_mantem_a_largada():
    pontos = np.array([[0.0, 0.0], [0.01, 0.0], [10.0, 0.0]])
    restantes = geometria.remover_pontos_repetidos(pontos, minimo_m=0.5)

    assert restantes.tolist() == [[0.0, 0.0], [10.0, 0.0]]


# --------------------------------------------------------------------------
# Distâncias e fechamento do loop
# --------------------------------------------------------------------------


def test_perimetro_inclui_o_segmento_de_fechamento():
    """O quadrado tem 4 lados; o quarto não vira ponto, mas conta na volta."""
    quadrado = np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]])
    distancias, perimetro = geometria.distancias_acumuladas(quadrado)

    assert perimetro == pytest.approx(40.0)
    assert distancias.tolist() == [0.0, 10.0, 20.0, 30.0]


def test_normalizacao_preserva_o_invariante_entre_geometria_e_distancia():
    """Escalar só a distância desacoplaria o mapa do motor — ver geometria.py."""
    quadrado = np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]])
    distancias, perimetro = geometria.distancias_acumuladas(quadrado)

    pontos, distancias, k = geometria.normalizar(quadrado, distancias, perimetro, 80)

    assert k == pytest.approx(2.0)
    passos = np.hypot(*np.diff(pontos, axis=0).T)
    assert passos == pytest.approx(np.diff(distancias))


# --------------------------------------------------------------------------
# Contrato D3, sobre os arquivos entregues
# --------------------------------------------------------------------------

CIRCUITOS_GERADOS = sorted(p.stem for p in CIRCUITS_DIR.glob("*.json"))


@pytest.fixture(params=CIRCUITOS_GERADOS)
def circuito(request):
    caminho = CIRCUITS_DIR / f"{request.param}.json"
    return json.loads(caminho.read_text(encoding="utf-8"))


def test_ha_circuitos_para_validar():
    """Guarda contra um `make circuitos` que não gerou nada e passaria despercebido."""
    assert CIRCUITOS_GERADOS, "nenhum JSON em circuits/ — rode `make circuitos`"


def test_schema_do_contrato(circuito):
    assert circuito["circuit_id"] in CIRCUITOS
    assert isinstance(circuito["length_m"], int)

    for ponto in circuito["points"]:
        assert set(ponto) == {"x", "y", "distance_m"}
        assert all(isinstance(v, float | int) for v in ponto.values())


def test_quantidade_de_pontos_na_faixa(circuito):
    assert PONTOS_MIN <= len(circuito["points"]) <= PONTOS_MAX


def test_length_m_bate_com_o_oficial(circuito):
    assert circuito["length_m"] == CIRCUITOS[circuito["circuit_id"]].length_m


def test_distancia_comeca_em_zero_e_e_crescente(circuito):
    distancias = [p["distance_m"] for p in circuito["points"]]

    assert distancias[0] == 0.0
    assert all(b > a for a, b in zip(distancias, distancias[1:], strict=False))


def test_distancia_total_bate_com_o_comprimento_oficial(circuito):
    """Critério de pronto do roadmap: erro abaixo de 1%."""
    pontos = circuito["points"]
    fechamento = math.dist(
        (pontos[-1]["x"], pontos[-1]["y"]),
        (pontos[0]["x"], pontos[0]["y"]),
    )
    total = pontos[-1]["distance_m"] + fechamento

    assert abs(total - circuito["length_m"]) / circuito["length_m"] < 0.01


def test_geometria_e_distancia_seguem_consistentes(circuito):
    """O que o mapa mede tem que ser o que o motor diz."""
    pontos = circuito["points"]

    for anterior, atual in zip(pontos, pontos[1:], strict=False):
        distancia_real = math.dist((anterior["x"], anterior["y"]), (atual["x"], atual["y"]))
        assert distancia_real == pytest.approx(
            atual["distance_m"] - anterior["distance_m"], abs=0.05
        )


def test_traçado_e_fechado(circuito):
    """O fim tem que voltar para perto da largada — é um circuito."""
    pontos = circuito["points"]
    fechamento = math.dist(
        (pontos[-1]["x"], pontos[-1]["y"]),
        (pontos[0]["x"], pontos[0]["y"]),
    )

    assert fechamento < 80.0


def test_meta_registra_a_proveniencia(circuito):
    """Sem isto o artefato não é reproduzível nem defensável na arguição."""
    assert set(circuito["meta"]) >= {
        "ano",
        "sessao",
        "piloto",
        "volta",
        "fastf1_versao",
        "epsilon_m",
        "fator_escala",
    }
