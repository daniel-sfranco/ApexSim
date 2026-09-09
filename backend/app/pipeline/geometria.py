"""Transformação da telemetria bruta na polyline do contrato D3.

A ordem das operações importa e não deve ser trocada:

    converter unidades -> limpar -> deduplicar -> RDP -> fechar o loop
    -> calcular distance_m -> normalizar pelo comprimento oficial

Duas inversões dessa ordem são erros silenciosos conhecidos. Reamostrar antes
do RDP destrói justamente os vértices que ele deveria escolher. E herdar a
coluna `Distance` da telemetria bruta faz o `distance_m` descrever arcos que a
polyline simplificada não tem mais — o frontend interpolaria posições erradas.
"""

import numpy as np

# O FastF1 entrega X e Y em décimos de metro. Converter antes de qualquer
# outra coisa: o epsilon do RDP é expresso em metros e a busca sairia por uma
# ordem de grandeza se a unidade estivesse errada.
DECIMOS_DE_METRO_POR_METRO = 10.0

# Pontos mais próximos que isso são amostras paradas ou ruído de GPS. Remover
# não é reamostrar: nenhum vértice de curva desaparece nessa escala.
DISTANCIA_MINIMA_M = 0.5


def converter_para_metros(x_decimos: np.ndarray, y_decimos: np.ndarray) -> np.ndarray:
    """Empilha X e Y num array (N, 2) em metros."""
    return np.column_stack([x_decimos, y_decimos]) / DECIMOS_DE_METRO_POR_METRO


def remover_pontos_repetidos(
    pontos: np.ndarray, minimo_m: float = DISTANCIA_MINIMA_M
) -> np.ndarray:
    """Descarta amostras consecutivas praticamente no mesmo lugar.

    Mantém sempre o primeiro ponto, que é a âncora da linha de largada.
    """
    if len(pontos) < 2:
        return pontos

    mantidos = [0]
    for indice in range(1, len(pontos)):
        if np.hypot(*(pontos[indice] - pontos[mantidos[-1]])) >= minimo_m:
            mantidos.append(indice)

    return pontos[mantidos]


def comprimentos_dos_segmentos(pontos: np.ndarray) -> np.ndarray:
    """Comprimento de cada segmento, incluindo o que fecha o circuito.

    O traçado é um loop, então o segmento do último ponto de volta ao primeiro
    é real e entra na conta. Devolve N valores para N pontos.
    """
    proximos = np.roll(pontos, -1, axis=0)
    return np.hypot(*(proximos - pontos).T)


def distancias_acumuladas(pontos: np.ndarray) -> tuple[np.ndarray, float]:
    """Calcula o `distance_m` de cada ponto e o perímetro total.

    `distance_m[0]` é zero por definição — é a linha de largada. O perímetro
    inclui o segmento de fechamento, que não aparece como ponto.
    """
    segmentos = comprimentos_dos_segmentos(pontos)
    distancias = np.concatenate([[0.0], np.cumsum(segmentos[:-1])])
    return distancias, float(segmentos.sum())


def normalizar(
    pontos: np.ndarray,
    distancias: np.ndarray,
    perimetro_m: float,
    length_oficial_m: int,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Escala geometria e distâncias para bater com o comprimento homologado.

    O perímetro medido nunca bate com o comprimento oficial, por dois motivos
    independentes: a telemetria é a trajetória real do carro, que corta as
    curvas, e o RDP encurta o percurso ao trocar arcos por cordas.

    A escala `k` é aplicada a x, y E distance_m — não só à distância. Escalar
    apenas a distância quebraria o invariante de que a distância entre dois
    pontos consecutivos é igual à diferença dos `distance_m` deles. A posição
    interpolada continuaria certa, mas tudo que mistura os dois espaços
    passaria a mentir: comprimento de zona de DRS desenhado sobre o mapa, gap
    convertido em pixels, animação por velocidade. Escalando os três, a
    consistência vale por construção e vira teste.

    O preço é que x e y deixam de ser coordenadas geográficas reais e passam a
    ser "metros de pista escalados". A distorção fica na casa de poucos por
    cento e é invisível na tela.
    """
    if perimetro_m <= 0:
        raise ValueError("perímetro precisa ser positivo")

    k = length_oficial_m / perimetro_m
    return pontos * k, distancias * k, k
