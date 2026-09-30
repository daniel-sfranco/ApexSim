"""Testes da reconciliação entre fontes, com tabelas mínimas montadas à mão.

Cada teste reproduz um caso real dos datasets (código FIA repetido, GP com nome
diferente, composto novo, numeração de volta deslocada).
"""

import pandas as pd
import pytest

from app.pipeline.reconciliacao import (
    ReconciliacaoInconsistente,
    mapear_circuitos,
    mapear_compostos,
    mapear_pilotos,
    verificar_sobreposicao,
)


@pytest.fixture
def historico() -> dict[str, pd.DataFrame]:
    races = pd.DataFrame(
        {
            "raceId": [1, 2, 3],
            "year": [2023, 2024, 2024],
            "circuitId": [18, 18, 14],
            "name": ["São Paulo Grand Prix", "São Paulo Grand Prix", "Italian Grand Prix"],
        }
    )
    circuits = pd.DataFrame(
        {
            "circuitId": [18, 14],
            "circuitRef": ["interlagos", "monza"],
            "name": ["Autódromo José Carlos Pace", "Autodromo Nazionale di Monza"],
            "country": ["Brazil", "Italy"],
        }
    )
    drivers = pd.DataFrame(
        {
            "driverId": [1, 2, 3, 4],
            "driverRef": ["max_verstappen", "vergne", "michael_schumacher", "mick_schumacher"],
            "code": ["VER", "VER", "MSC", "MSC"],
            "forename": ["Max", "Jean-Éric", "Michael", "Mick"],
            "surname": ["Verstappen", "Vergne", "Schumacher", "Schumacher"],
        }
    )
    # Em 2023-2024 só Max e Mick correram; Vergne e Michael são de outras épocas.
    results = pd.DataFrame({"raceId": [1, 2, 3, 1], "driverId": [1, 1, 1, 4]})
    return {"races": races, "circuits": circuits, "drivers": drivers, "results": results}


def test_gp_vira_slug_do_circuito(historico):
    tabela = mapear_circuitos(historico, {"São Paulo Grand Prix"}, {"Italian Grand Prix"})

    por_gp = tabela.set_index("gp_nome")
    assert por_gp.loc["São Paulo Grand Prix", "circuit_id"] == "interlagos"
    assert por_gp.loc["São Paulo Grand Prix", "temporadas"] == "2023;2024"
    assert por_gp.loc["Italian Grand Prix", "arquivo_alexjr"] == "Italian_Grand_Prix.csv"
    assert bool(por_gp.loc["Italian Grand Prix", "no_projeto"]) is True


def test_gp_sem_correspondencia_derruba_a_reconciliacao(historico):
    with pytest.raises(ReconciliacaoInconsistente, match="Brazilian Grand Prix"):
        mapear_circuitos(historico, {"Brazilian Grand Prix"}, set())


def test_codigo_repetido_e_resolvido_pela_temporada(historico):
    """VER em 2024 é o Max, não o Vergne; MSC em 2023 é o Mick, não o Michael."""
    participantes = pd.DataFrame(
        {"Ano": [2024, 2023], "codigo": ["VER", "MSC"], "fontes": ["pneus", "pneus"]}
    )

    tabela, sem_match = mapear_pilotos(historico, participantes)

    por_codigo = tabela.set_index("codigo")
    assert sem_match.empty
    assert por_codigo.loc["VER", "driverRef"] == "max_verstappen"
    assert por_codigo.loc["VER", "codigo_repetido_com"] == "vergne"
    assert por_codigo.loc["MSC", "driverRef"] == "mick_schumacher"


def test_piloto_fora_do_historico_e_reportado(historico):
    participantes = pd.DataFrame({"Ano": [2024], "codigo": ["XYZ"], "fontes": ["pneus"]})

    tabela, sem_match = mapear_pilotos(historico, participantes)

    assert tabela.empty
    assert sem_match["codigo"].tolist() == ["XYZ"]


def test_codigo_repetido_na_mesma_temporada_derruba(historico):
    historico["results"] = pd.concat(
        [historico["results"], pd.DataFrame({"raceId": [2], "driverId": [2]})]
    )  # Vergne "correndo" em 2024 junto com o Max
    participantes = pd.DataFrame({"Ano": [2024], "codigo": ["VER"], "fontes": ["pneus"]})

    with pytest.raises(ReconciliacaoInconsistente, match="mesma temporada"):
        mapear_pilotos(historico, participantes)


def test_compostos_conhecidos_sao_mapeados_e_desconhecidos_descartados():
    observados = pd.DataFrame(
        {
            "fonte": ["pneus", "pneus", "alexjr"],
            "Compound": ["SOFT", "TEST_UNKNOWN", "SOFT"],
            "n_voltas": [10, 3, 5],
        }
    )

    tabela = mapear_compostos(observados).set_index("valor_fonte")

    assert tabela.loc["SOFT", "codigo_banco"] == "SOFT"
    assert tabela.loc["SOFT", "chave_fisica"] == "soft"
    assert tabela.loc["SOFT", "n_voltas"] == 15
    assert tabela.loc["TEST_UNKNOWN", "acao"] == "descartado"


def test_composto_novo_sem_regra_derruba():
    observados = pd.DataFrame({"fonte": ["pneus"], "Compound": ["HYPERSOFT"], "n_voltas": [1]})

    with pytest.raises(ReconciliacaoInconsistente, match="HYPERSOFT"):
        mapear_compostos(observados)


def _volta(gp, piloto, volta, tempo, composto="MEDIUM", **extra):
    return dict(GP=gp, Driver=piloto, LapNumber=volta, LapTime=tempo, Compound=composto, **extra)


def test_sobreposicao_detecta_numeracao_de_volta_deslocada():
    """Mônaco 2024: as duas fontes contam as voltas com 1 de diferença."""
    pneus = pd.DataFrame(
        [_volta("Monaco Grand Prix", "LEC", v, 80.0 + v, Ano=2024, Sessao="R") for v in (2, 3, 4)]
        + [_volta("Italian Grand Prix", "LEC", 2, 81.0, Ano=2024, Sessao="R")]
    )
    alexjr = pd.DataFrame(
        [_volta("Monaco Grand Prix", "LEC", v - 1, 80.0 + v) for v in (2, 3, 4)]
        + [_volta("Italian Grand Prix", "LEC", 2, 81.0)]
    )

    tabela = verificar_sobreposicao(pneus, alexjr).set_index("gp_nome")

    assert tabela.loc["Monaco Grand Prix", "deslocamento_de_volta"] == 1
    assert tabela.loc["Monaco Grand Prix", "tempo_igual"] == 3
    assert tabela.loc["Monaco Grand Prix", "tempo_igual_sem_deslocamento"] == 0
    assert tabela.loc["Italian Grand Prix", "deslocamento_de_volta"] == 0
    assert tabela.loc["TOTAL", "pct_tempo_igual"] == 100.0


def test_sobreposicao_ignora_treinos_e_mede_divergencia_de_composto():
    pneus = pd.DataFrame(
        [
            _volta("Belgian Grand Prix", "HAM", 2, 100.0, "HARD", Ano=2024, Sessao="R"),
            _volta("Belgian Grand Prix", "HAM", 3, 100.0, "SOFT", Ano=2024, Sessao="FP1"),
        ]
    )
    alexjr = pd.DataFrame([_volta("Belgian Grand Prix", "HAM", 2, 100.0, "MEDIUM")])

    linha = verificar_sobreposicao(pneus, alexjr).set_index("gp_nome").loc["Belgian Grand Prix"]

    assert linha["achadas_em_pneus"] == 1
    assert linha["composto_igual"] == 0
    assert linha["pct_composto_diverge"] == 100.0
