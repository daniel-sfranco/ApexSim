"""Testes do algoritmo de simplificação, sobre geometria sintética."""

import numpy as np
import pytest

from app.pipeline.rdp import (
    EpsilonNaoConvergiu,
    _distancia_ponto_reta,
    buscar_epsilon,
    simplificar,
)


def test_reta_colapsa_para_os_extremos():
    """Pontos sobre uma reta não carregam informação de forma."""
    reta = np.column_stack([np.linspace(0, 100, 50), np.zeros(50)])
    assert simplificar(reta, epsilon=0.5).tolist() == [0, 49]


def test_preserva_vertice_acima_da_tolerancia():
    triangulo = np.array([[0.0, 0.0], [50.0, 10.0], [100.0, 0.0]])
    assert simplificar(triangulo, epsilon=1.0).tolist() == [0, 1, 2]


def test_descarta_vertice_abaixo_da_tolerancia():
    quase_reta = np.array([[0.0, 0.0], [50.0, 0.1], [100.0, 0.0]])
    assert simplificar(quase_reta, epsilon=1.0).tolist() == [0, 2]


def test_extremos_sempre_sobrevivem():
    """O índice 0 é a linha de largada — âncora de todas as zonas do Daniel."""
    angulos = np.linspace(0, 2 * np.pi, 500, endpoint=False)
    circulo = np.column_stack([np.cos(angulos), np.sin(angulos)]) * 100

    indices = simplificar(circulo, epsilon=5.0)
    assert indices[0] == 0
    assert indices[-1] == len(circulo) - 1


def test_mais_tolerancia_nunca_produz_mais_pontos():
    """Monotonicidade é o que torna a bissecção da busca de epsilon válida."""
    rng = np.random.default_rng(42)
    ruidoso = np.cumsum(rng.normal(size=(2000, 2)), axis=0)

    contagens = [len(simplificar(ruidoso, eps)) for eps in [0.01, 0.1, 1.0, 10.0, 100.0]]
    assert contagens == sorted(contagens, reverse=True)


def test_nenhum_ponto_descartado_se_afasta_mais_que_epsilon():
    """Esta é a garantia de fidelidade do traçado.

    Um segmento longo não é problema desde que a pista seja reta ali — o que
    importa é que nenhum ponto do traçado original fique longe da polyline
    simplificada. É por isso que não testamos comprimento máximo de segmento.
    """
    rng = np.random.default_rng(3)
    traçado = np.cumsum(rng.normal(size=(1500, 2)), axis=0)
    epsilon = 2.0

    indices = simplificar(traçado, epsilon)
    simplificado = traçado[indices]

    for inicio, fim in zip(indices, indices[1:], strict=False):
        descartados = traçado[inicio + 1 : fim]
        if len(descartados) == 0:
            continue
        desvios = _distancia_ponto_reta(descartados, traçado[inicio], traçado[fim])
        assert desvios.max() <= epsilon

    assert len(simplificado) < len(traçado)


def test_busca_epsilon_atinge_a_faixa_pedida():
    rng = np.random.default_rng(7)
    traçado = np.cumsum(rng.normal(size=(5000, 2)), axis=0)

    epsilon, indices = buscar_epsilon(traçado, n_min=250, n_max=400)
    assert 250 <= len(indices) <= 400
    assert epsilon > 0


def test_busca_falha_alto_quando_nao_ha_pontos_suficientes():
    """Devolver um resultado fora da faixa quebraria o consumidor em silêncio."""
    poucos = np.column_stack([np.linspace(0, 10, 20), np.zeros(20)])

    with pytest.raises(EpsilonNaoConvergiu):
        buscar_epsilon(poucos, n_min=250, n_max=400)
