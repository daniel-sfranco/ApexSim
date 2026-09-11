"""Configuração central do backend.

Toda constante de caminho, conexão e parâmetro de modelo vive aqui — nunca
hardcoded no meio da lógica (convenção da seção 6 do CLAUDE.md).
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Raiz do repositório: config.py -> app/ -> backend/ -> raiz
REPO_ROOT = Path(__file__).resolve().parents[2]

# Saída do contrato D3, consumida por Daniel (anotação) e Anderson (minimapa).
CIRCUITS_DIR = REPO_ROOT / "circuits"

# Datasets brutos e cache do FastF1 — fora do controle de versão.
DATA_RAW_DIR = REPO_ROOT / "data" / "raw"


class Settings(BaseSettings):
    """Configuração lida do ambiente, com defaults que funcionam no compose."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://apexsim:apexsim@db:5432/apexsim"

    # Volume nomeado no docker-compose. O cache é a mitigação do rate limit do
    # Jolpica: sem ele, cada subida do ambiente rebaixa centenas de MB.
    fastf1_cache_dir: Path = Path("/cache/fastf1")


settings = Settings()
