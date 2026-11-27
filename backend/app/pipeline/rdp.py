"""Simplificação de polyline por Ramer-Douglas-Peucker.

O traçado bruto do FastF1 tem milhares de pontos amostrados no tempo. O
contrato D3 pede algo entre 250 e 400 pontos preservando a forma do circuito,
e é isso que o RDP faz: mantém os vértices onde a curva realmente muda de
direção e descarta os pontos que já estão sobre a reta entre dois vizinhos.

Implementado à mão em vez de usar `shapely.simplify` por duas razões: evita
uma dependência geoespacial pesada por causa de uma função, e é um algoritmo
que precisamos conseguir explicar na arguição.
"""

import numpy as np


def _distancia_ponto_reta(pontos: np.ndarray, inicio: np.ndarray, fim: np.ndarray) -> np.ndarray:
    """Distância perpendicular de cada ponto até a reta que liga início a fim.

    Vetorizado: recebe (N, 2) e devolve (N,). Quando início e fim coincidem, a
    reta degenera num ponto e a distância vira a euclidiana até ele.
    """
    segmento = fim - inicio
    comprimento = np.hypot(*segmento)

    if comprimento == 0:
        return np.hypot(*(pontos - inicio).T)

    # Produto vetorial 2D dividido pelo comprimento do segmento: a área do
    # paralelogramo dividida pela base dá a altura, que é a distância buscada.
    deslocamento = pontos - inicio
    return np.abs(segmento[0] * deslocamento[:, 1] - segmento[1] * deslocamento[:, 0]) / comprimento


def simplificar(pontos: np.ndarray, epsilon: float) -> np.ndarray:
    """Aplica RDP e devolve os índices dos pontos preservados, em ordem.

    `epsilon` é a tolerância em metros: nenhum ponto descartado está a mais do
    que essa distância da polyline resultante. Os extremos são sempre
    preservados — é o que garante que o índice 0 continue sendo a linha de
    largada.

    Usa uma pilha explícita em vez de recursão porque a entrada tem dezenas de
    milhares de pontos e a recursão natural do algoritmo estouraria o limite
    do Python.
    """
    n = len(pontos)
    if n < 3:
        return np.arange(n)

    manter = np.zeros(n, dtype=bool)
    manter[0] = manter[-1] = True

    pilha = [(0, n - 1)]
    while pilha:
        inicio, fim = pilha.pop()
        if fim <= inicio + 1:
            continue

        miolo = pontos[inicio + 1 : fim]
        distancias = _distancia_ponto_reta(miolo, pontos[inicio], pontos[fim])

        indice_local = int(np.argmax(distancias))
        if distancias[indice_local] <= epsilon:
            continue

        # O ponto mais distante fica; os dois trechos que ele cria são
        # avaliados da mesma forma.
        divisor = inicio + 1 + indice_local
        manter[divisor] = True
        pilha.append((inicio, divisor))
        pilha.append((divisor, fim))

    return np.flatnonzero(manter)


class EpsilonNaoConvergiu(RuntimeError):
    """A busca não achou tolerância que caiba na faixa de pontos do contrato."""


def buscar_epsilon(
    pontos: np.ndarray,
    n_min: int,
    n_max: int,
    max_iteracoes: int = 60,
) -> tuple[float, np.ndarray]:
    """Acha um epsilon cuja simplificação caia entre `n_min` e `n_max` pontos.

    O RDP recebe uma tolerância, não um número-alvo de pontos, então é preciso
    procurar. A contagem de pontos é monótona não-crescente em epsilon (mais
    tolerância nunca produz mais pontos), o que permite bissecção.

    Primeiro faz bracketing exponencial para achar um teto que já simplifica
    demais, depois bisseciona entre o piso e o teto. Devolve o epsilon e os
    índices preservados.

    Levanta `EpsilonNaoConvergiu` em vez de devolver um resultado fora da faixa:
    um arquivo com 800 pontos quebraria o consumidor silenciosamente, e é
    melhor a ingestão falhar alto.
    """
    if n_min > n_max:
        raise ValueError("n_min não pode ser maior que n_max")

    contar = lambda eps: simplificar(pontos, eps)  # noqa: E731

    # Piso praticamente nulo: só descarta pontos exatamente colineares. Um
    # piso de 0,1 m já era grande demais para Monza, que é quase toda reta e
    # caía para 240 pontos antes mesmo da busca começar.
    eps_baixo = 1e-6
    indices = contar(eps_baixo)
    if len(indices) <= n_max:
        # O traçado já é simples demais para precisar de busca.
        if len(indices) < n_min:
            raise EpsilonNaoConvergiu(
                f"nem com epsilon mínimo há {n_min} pontos: {len(indices)} disponíveis"
            )
        return eps_baixo, indices

    # Teto: dobra até simplificar abaixo do mínimo.
    eps_alto = eps_baixo
    for _ in range(max_iteracoes):
        eps_alto *= 2
        if len(contar(eps_alto)) < n_min:
            break
    else:
        raise EpsilonNaoConvergiu("não foi possível encontrar um teto para epsilon")

    for _ in range(max_iteracoes):
        eps_meio = (eps_baixo + eps_alto) / 2
        indices = contar(eps_meio)
        n = len(indices)

        if n_min <= n <= n_max:
            return eps_meio, indices

        # Pontos demais pede mais tolerância; de menos pede menos.
        if n > n_max:
            eps_baixo = eps_meio
        else:
            eps_alto = eps_meio

        if eps_alto - eps_baixo < 1e-4:
            break

    raise EpsilonNaoConvergiu(
        f"busca terminou fora da faixa [{n_min}, {n_max}] com {len(indices)} pontos"
    )
