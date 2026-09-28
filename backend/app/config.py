"""Configuração central do backend.

Toda constante de caminho, conexão e parâmetro de modelo vive aqui — nunca
hardcoded no meio da lógica (convenção da seção 6 do CLAUDE.md).
"""

from dataclasses import dataclass
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Raiz do repositório: config.py -> app/ -> backend/ -> raiz
REPO_ROOT = Path(__file__).resolve().parents[2]

# Saída do contrato D3, consumida por Daniel (anotação) e Anderson (minimapa).
CIRCUITS_DIR = REPO_ROOT / "circuits"

# Datasets brutos e cache do FastF1 — fora do controle de versão.
DATA_DIR = REPO_ROOT / "data"
DATA_RAW_DIR = DATA_DIR / "raw"

# Saídas pequenas e versionadas da ingestão dos datasets: as tabelas de
# mapeamento entre fontes e as curvas de degradação entregues ao Isaac.
MAPEAMENTOS_DIR = DATA_DIR / "mapeamentos"
CURVAS_DIR = DATA_DIR / "curvas_degradacao"


# --------------------------------------------------------------------------
# Geometria dos circuitos (contrato D3)
# --------------------------------------------------------------------------

# Faixa de pontos exigida pelo contrato: densa o bastante para o traçado ficar
# reconhecível na tela, esparsa o bastante para o frontend animar 20 carros.
PONTOS_MIN = 250
PONTOS_MAX = 400


@dataclass(frozen=True)
class Circuito:
    """Um circuito a ser ingerido, com o comprimento oficial como âncora.

    O `length_m` NÃO é derivado da telemetria: ele é o valor homologado, e é
    contra ele que a polyline é normalizada. Por isso cada valor carrega a
    fonte de onde veio.
    """

    circuit_id: str
    rodada: int
    evento: str
    length_m: int


# Comprimentos oficiais em metros.
#
# Fonte primária: FIA, "List of FIA Licensed Circuits", atualizada em
# 2026-03-31 — https://api.fia.com/sites/default/files/circuits_fia20260331_0.pdf
# Conferido contra as páginas oficiais de circuito da Formula1.com
# (ex.: formula1.com/en/racing/2024/brazil/circuit → 4.309 km).
# Acesso em 2026-09-08.
# Os circuitos são identificados pelo NÚMERO DA RODADA, não pelo nome. O
# FastF1 faz correspondência aproximada de nomes e erra: "Interlagos" foi
# resolvido para o Dutch Grand Prix (Zandvoort) durante a implementação, o que
# geraria o traçado errado sem nenhum erro visível.
CIRCUITOS: dict[str, Circuito] = {
    "interlagos": Circuito("interlagos", 21, "São Paulo Grand Prix", 4309),
    "monza": Circuito("monza", 16, "Italian Grand Prix", 5793),
    "monaco": Circuito("monaco", 8, "Monaco Grand Prix", 3337),
}

# Sessão usada para extrair o traçado. Qualifying dá a volta mais limpa do fim
# de semana: pista seca, sem tráfego e sem safety car. A corrida de Mônaco de
# 2024, por exemplo, teve bandeira vermelha.
ANO_TELEMETRIA = 2024
SESSAO_TELEMETRIA = "Q"


# --------------------------------------------------------------------------
# Datasets do Kaggle e reconciliação entre fontes
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DatasetKaggle:
    """Um dataset a baixar. `pasta` é o nome dentro de `data/raw/`."""

    slug: str
    pasta: str


DATASETS_KAGGLE = (
    DatasetKaggle("jtrotman/formula-1-race-data", "formula-1-race-data"),
    DatasetKaggle(
        "vanshbatra26/f1-tyre-strategy-engine-datasets", "f1-tyre-strategy-engine-datasets"
    ),
    DatasetKaggle(
        "alexjr2001/formula-1-dataset-race-data-and-telemetry",
        "formula-1-dataset-race-data-and-telemetry",
    ),
)

# Caminhos dentro de cada dataset (conferidos em 2026-09-28).
PASTA_PNEUS = DATA_RAW_DIR / "f1-tyre-strategy-engine-datasets" / "F1-Tyre-Strategy-Engine"
PASTA_HISTORICO = DATA_RAW_DIR / "formula-1-race-data"
PASTA_VOLTAS_ALEXJR = (
    DATA_RAW_DIR / "formula-1-dataset-race-data-and-telemetry" / "Directories" / "LapData"
)

# Temporadas cobertas pelo dataset de pneus. O `alexjr2001` é a temporada 2024
# (as voltas coincidem com as do dataset de pneus — ver `sobreposicao_fontes.csv`).
TEMPORADAS_PNEUS = (2023, 2024)

# Temporada cujo grid vira piloto e equipe no banco (`make seed`). O código FIA
# se repete no histórico, então o seed carrega uma temporada só; dentro dela
# ele é único (`drivers.code` é UNIQUE).
TEMPORADA_DO_SEED = 2024

# Tradução do valor de composto de cada fonte para o código do banco. `None`
# significa "descartar a volta": o composto é desconhecido e não dá para
# atribuí-la a nenhuma curva. Um valor que não estiver aqui derruba a
# reconciliação em vez de passar em silêncio.
COMPOSTOS_FONTE_PARA_BANCO: dict[str, str | None] = {
    "SOFT": "SOFT",
    "MEDIUM": "MEDIUM",
    "HARD": "HARD",
    "INTERMEDIATE": "INTERMEDIATE",
    "WET": "WET",
    "UNKNOWN": None,
    "TEST_UNKNOWN": None,
}

# Nomes em português dos compostos (seção 1 do CLAUDE.md).
COMPOSTOS_NOME_PT = {
    "SOFT": "Macio",
    "MEDIUM": "Médio",
    "HARD": "Duro",
    "INTERMEDIATE": "Intermediário",
    "WET": "Chuva",
}


# --------------------------------------------------------------------------
# Curvas de degradação de pneu (entrega D5, consumida pelo Isaac)
# --------------------------------------------------------------------------

# Compostos de pneu seco. Intermediário e chuva dependem do clima e ficam fora.
COMPOSTOS_SECOS = ("SOFT", "MEDIUM", "HARD")

# O dataset mistura treinos livres, classificação e corrida. Só a corrida tem
# carga de combustível e ritmo comparáveis.
SESSAO_CORRIDA = "R"

# ESCOLHAS DE MODELAGEM (não são física; são filtros de dados, e por isso há
# uma análise de sensibilidade em `degradacao.py`):
#
# Volta mais lenta que este múltiplo da mediana do piloto naquela corrida é
# descartada como anômala (Safety Car, VSC, bandeira vermelha, erro). O valor
# empresta o limite de 107% que a FIA usa na classificação.
LIMITE_VOLTA_ANOMALA = 1.07

# Uma idade de pneu só entra na curva se tiver pelo menos este número de voltas
# limpas. Abaixo disso a estimativa é ruído e a curva "descola" dos dados.
MIN_VOLTAS_POR_IDADE = 100

# Idade de referência: a menor com volta limpa (a volta 1 do stint é a de saída
# do box e é descartada). A curva entregue é a perda de tempo relativa a ela.
IDADE_REFERENCIA = 2

# Estimativas do Isaac em `notebooks/fisica-e-eventos/physics.py` (TYRE_PARAMS).
# Estão aqui SÓ para o gráfico comparar estimado × medido; o que o motor usa
# continua sendo o `physics.py`. São palpites dentro da faixa da literatura,
# não medições.
PARAMETROS_ISAAC_ESTIMADOS = {
    "SOFT": dict(k1_quad=0.0009, k2_lin=0.075, cliff_age=14, cliff_delta=1.2, cliff_beta=0.9),
    "MEDIUM": dict(k1_quad=0.0006, k2_lin=0.058, cliff_age=22, cliff_delta=0.8, cliff_beta=0.7),
    "HARD": dict(k1_quad=0.0004, k2_lin=0.048, cliff_age=32, cliff_delta=0.5, cliff_beta=0.5),
}


class Settings(BaseSettings):
    """Configuração lida do ambiente, com defaults que funcionam no compose."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://apexsim:apexsim@db:5432/apexsim"

    # Volume nomeado no docker-compose. O cache é a mitigação do rate limit do
    # Jolpica: sem ele, cada subida do ambiente rebaixa centenas de MB.
    fastf1_cache_dir: Path = Path("/cache/fastf1")


settings = Settings()
