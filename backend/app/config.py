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

# Ferramentas internas e mapas semânticos anotados (contrato D4).
TOOLS_DIR = REPO_ROOT / "tools"
TRACK_EDITOR_DIR = TOOLS_DIR / "track_editor"
TRACK_MAPS_DIR = REPO_ROOT / "track_maps"

# Datasets brutos e cache do FastF1 — fora do controle de versão.
DATA_RAW_DIR = REPO_ROOT / "data" / "raw"


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


class Settings(BaseSettings):
    """Configuração lida do ambiente, com defaults que funcionam no compose."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://apexsim:apexsim@db:5432/apexsim"

    # Volume nomeado no docker-compose. O cache é a mitigação do rate limit do
    # Jolpica: sem ele, cada subida do ambiente rebaixa centenas de MB.
    fastf1_cache_dir: Path = Path("/cache/fastf1")


settings = Settings()
