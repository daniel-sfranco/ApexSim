"""Testes das curvas de degradação, sobre dados sintéticos com resposta conhecida.

Não dependem de `data/raw/`: o CI não baixa datasets. O teste que mais importa é
o de recuperação: gera corridas com uma curva de degradação conhecida e confere
se o estimador a reencontra, o que só acontece se o modelo de efeitos fixos
estiver implementado direito.
"""

import numpy as np
import pandas as pd
import pytest

from app.config import IDADE_REFERENCIA
from app.pipeline import degradacao
from app.pipeline.degradacao import (
    CurvaMedida,
    ajustar_forma,
    estimar_curvas,
    filtrar_voltas_limpas,
)


def _curva_verdadeira(idade):
    """Perda de tempo verdadeira (s) relativa à idade de referência."""
    a = np.asarray(idade, dtype=float)
    return 0.02 * (a - IDADE_REFERENCIA) + 0.003 * (a**2 - IDADE_REFERENCIA**2)


def _corridas_sinteticas(semente: int = 0, ruido: float = 0.10) -> pd.DataFrame:
    """12 corridas x 10 pilotos, 2 stints cada, com base, combustível e composto."""
    rng = np.random.default_rng(semente)
    deslocamento = {"SOFT": -0.4, "MEDIUM": 0.0, "HARD": 0.3}
    linhas = []
    for ano in (2023, 2024):
        for gp in range(6):
            base_pista = rng.uniform(70, 100)
            inclinacao = -0.05  # o carro fica mais leve e a pista melhora
            for piloto in range(10):
                base = base_pista + rng.normal(0, 0.6)
                volta = 1
                for stint in (1, 2):
                    composto = rng.choice(["SOFT", "MEDIUM", "HARD"])
                    duracao = int(rng.integers(14, 24))
                    for idade in range(1, duracao + 1):
                        tempo = (
                            base
                            + inclinacao * volta
                            + deslocamento[composto]
                            + _curva_verdadeira(idade)
                            + rng.normal(0, ruido)
                        )
                        linhas.append(
                            dict(
                                Ano=ano,
                                GP=f"GP{gp}",
                                Driver=f"D{piloto}",
                                Stint=stint,
                                LapNumber=volta + 1,
                                Compound=composto,
                                TyreLife=idade,
                                LapTime=tempo,
                                Chuva=False,
                                Sessao="R",
                            )
                        )
                        volta += 1
    return pd.DataFrame(linhas)


@pytest.fixture
def poucas_voltas_bastam(monkeypatch):
    """O mínimo de 100 voltas por idade é para os dados reais; nos sintéticos sobram menos."""
    monkeypatch.setattr(degradacao, "MIN_VOLTAS_POR_IDADE", 8)


def test_estimador_recupera_a_curva_verdadeira(poucas_voltas_bastam):
    """O teste que prova o modelo: base, combustível e composto não podem vazar para a curva."""
    limpas = filtrar_voltas_limpas(_corridas_sinteticas())

    curvas = estimar_curvas(limpas)

    for composto, curva in curvas.items():
        for idade in (6, 10, 14):
            i = int(np.where(curva.idades == idade)[0][0])
            assert curva.delta_s[i] == pytest.approx(_curva_verdadeira(idade), abs=0.15), (
                f"{composto} idade {idade}"
            )


def test_referencia_tem_perda_zero_e_erro_zero(poucas_voltas_bastam):
    curvas = estimar_curvas(filtrar_voltas_limpas(_corridas_sinteticas()))

    for curva in curvas.values():
        assert curva.idades[0] == IDADE_REFERENCIA
        assert curva.delta_s[0] == 0.0
        assert curva.erro_padrao_s[0] == 0.0


def test_idade_com_poucas_voltas_fica_fora_da_curva(monkeypatch):
    monkeypatch.setattr(degradacao, "MIN_VOLTAS_POR_IDADE", 10_000)

    assert degradacao.idade_maxima_suportada(
        filtrar_voltas_limpas(_corridas_sinteticas()), "SOFT"
    ) == (IDADE_REFERENCIA)


# --- filtros ----------------------------------------------------------------


def _pilotos_de_teste(n_voltas: int = 10, **sobrescreve) -> pd.DataFrame:
    """Um piloto, um stint de `n_voltas` voltas limpas (voltas 2 a n_voltas + 1)."""
    linhas = []
    for i in range(n_voltas):
        linha = dict(
            Ano=2024,
            GP="Teste",
            Driver="AAA",
            Stint=1,
            LapNumber=i + 2,
            Compound="MEDIUM",
            TyreLife=i + 1,
            LapTime=90.0,
            Chuva=False,
            Sessao="R",
        )
        linha.update(sobrescreve)
        linhas.append(linha)
    return pd.DataFrame(linhas)


def test_volta_de_saida_e_de_entrada_do_box_sao_descartadas():
    limpas = filtrar_voltas_limpas(_pilotos_de_teste(10))

    # das voltas 2..11 saem a primeira (saída do box) e a última (entrada)
    assert limpas["LapNumber"].tolist() == list(range(3, 11))


def test_so_corrida_conta():
    treino = _pilotos_de_teste(10, Sessao="FP1")
    sem_sessao = _pilotos_de_teste(10, Sessao=np.nan)

    assert filtrar_voltas_limpas(pd.concat([treino, sem_sessao])).empty


def test_chuva_e_leitura_de_clima_ausente_ficam_de_fora():
    molhada = _pilotos_de_teste(10, Chuva=True)
    sem_clima = _pilotos_de_teste(10, Chuva=np.nan, Driver="BBB")

    assert filtrar_voltas_limpas(pd.concat([molhada, sem_clima])).empty


def test_composto_desconhecido_ou_de_chuva_fica_de_fora():
    for composto in ("UNKNOWN", "INTERMEDIATE", "WET"):
        assert filtrar_voltas_limpas(_pilotos_de_teste(10, Compound=composto)).empty


def test_volta_muito_lenta_e_descartada_como_anomala():
    voltas = _pilotos_de_teste(12)
    voltas.loc[5, "LapTime"] = 140.0  # safety car

    limpas = filtrar_voltas_limpas(voltas)

    assert 140.0 not in limpas["LapTime"].tolist()
    assert len(limpas) == 9  # 12 - saída - entrada - a anômala


def test_volta_sem_tempo_nao_desloca_o_limite_do_stint():
    """Uma volta sem tempo não pode virar, por engano, a 'primeira' do stint."""
    voltas = _pilotos_de_teste(10)
    voltas.loc[0, "LapTime"] = np.nan  # a volta de saída do box, sem tempo

    limpas = filtrar_voltas_limpas(voltas)

    assert limpas["LapNumber"].min() == 3


# --- forma paramétrica -------------------------------------------------------


def _curva_de_teste(delta: np.ndarray, idades: np.ndarray, erro: float = 0.04) -> CurvaMedida:
    return CurvaMedida(
        "SOFT", idades, delta, np.where(idades == idades[0], 0.0, erro), np.full(len(idades), 500)
    )


def test_curva_quadratica_nao_gera_cliff():
    idades = np.arange(IDADE_REFERENCIA, 30)
    curva = _curva_de_teste(_curva_verdadeira(idades), idades)

    forma = ajustar_forma(curva)

    assert forma["cliff"] is None
    assert forma["k1_quad"] == pytest.approx(0.003, abs=1e-3)
    assert forma["k2_lin"] == pytest.approx(0.02, abs=5e-3)


def test_cliff_real_no_interior_e_reconhecido():
    idades = np.arange(IDADE_REFERENCIA, 36)
    salto = degradacao.perda_de_tempo(idades, 0.0006, 0.05, 20.0, 1.5, 1.2)
    curva = _curva_de_teste(salto - salto[0], idades)

    forma = ajustar_forma(curva)

    assert forma["cliff"] is not None
    assert forma["cliff"]["cliff_age"] == pytest.approx(20.0, abs=1.5)
    assert forma["cliff"]["cliff_delta"] == pytest.approx(1.5, abs=0.4)


def test_cliff_colado_no_fim_dos_dados_nao_e_aceito():
    """Sem dados depois do salto, ele não é distinguível de uma curva mais inclinada."""
    idades = np.arange(IDADE_REFERENCIA, 30)
    salto = degradacao.perda_de_tempo(idades, 0.0006, 0.05, 28.0, 2.0, 1.5)
    curva = _curva_de_teste(salto - salto[0], idades)

    assert ajustar_forma(curva)["cliff"] is None


def test_curva_concava_marca_k1_no_limite():
    """Se os dados são côncavos, k1 >= 0 encosta em 0 e isso tem que ser avisado."""
    idades = np.arange(IDADE_REFERENCIA, 30)
    concava = 0.25 * (idades - IDADE_REFERENCIA) - 0.004 * (idades - IDADE_REFERENCIA) ** 2
    curva = _curva_de_teste(concava, idades)

    assert ajustar_forma(curva)["qualidade"]["k1_no_limite_inferior"] is True
