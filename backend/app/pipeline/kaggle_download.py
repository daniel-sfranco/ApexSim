"""Baixa os datasets do Kaggle para `data/raw/` (fora do controle de versão).

Executar com `make dados` (ou `make kaggle` para só baixar). É idempotente:
uma pasta que já tem conteúdo é pulada, então rodar duas vezes não rebaixa
nada. Use `--forcar` para baixar de novo.

Credencial: o token da API do Kaggle (formato `KGAT_...`) vem da variável de
ambiente `KAGGLE_API_TOKEN` ou do arquivo `~/.kaggle/access_token`. Nunca vai
para o repositório: `.env` está no `.gitignore`.

Usa só a biblioteca padrão de propósito: baixar três zips não justifica
instalar o cliente do Kaggle (e uma dependência a mais para cinco máquinas).
"""

import argparse
import logging
import os
import shutil
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urlparse

from app.config import DATA_RAW_DIR, DATASETS_KAGGLE, DatasetKaggle

logger = logging.getLogger(__name__)

URL_DOWNLOAD = "https://www.kaggle.com/api/v1/datasets/download/{slug}"
ARQUIVO_TOKEN = Path.home() / ".kaggle" / "access_token"


class TokenAusente(RuntimeError):
    """Não há credencial do Kaggle configurada."""


def ler_token() -> str:
    """Devolve o token da variável de ambiente ou do arquivo, nessa ordem."""
    token = os.environ.get("KAGGLE_API_TOKEN", "").strip()
    if not token and ARQUIVO_TOKEN.is_file():
        token = ARQUIVO_TOKEN.read_text(encoding="utf-8").strip()
    if not token:
        raise TokenAusente(
            "Token do Kaggle não encontrado. Crie um em kaggle.com > Settings > API > "
            "Create Token e coloque em KAGGLE_API_TOKEN (no .env) ou em ~/.kaggle/access_token."
        )
    return token


class _RedirectSemCredencial(urllib.request.HTTPRedirectHandler):
    """Segue redirects, mas tira o token quando o destino é outro servidor.

    O Kaggle redireciona o download para um armazenamento com URL assinada. O
    `urllib` reenviaria o cabeçalho `Authorization` para esse terceiro; o
    `curl -L` não faz isso, e aqui replicamos o comportamento seguro.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        novo = super().redirect_request(req, fp, code, msg, headers, newurl)
        if novo is not None and urlparse(newurl).netloc != urlparse(req.full_url).netloc:
            novo.remove_header("Authorization")
        return novo


def extrair_zip_seguro(caminho_zip: Path, destino: Path) -> int:
    """Extrai o zip recusando membros que escapariam de `destino` (zip-slip)."""
    raiz = destino.resolve()
    with zipfile.ZipFile(caminho_zip) as z:
        for membro in z.namelist():
            if not (raiz / membro).resolve().is_relative_to(raiz):
                raise ValueError(f"Caminho suspeito no zip: {membro!r}")
        z.extractall(destino)
        return len(z.namelist())


def baixar(dataset: DatasetKaggle, token: str, raiz: Path, forcar: bool = False) -> str:
    """Baixa um dataset. Devolve "baixado" ou "ja_existia"."""
    destino = raiz / dataset.pasta
    if destino.is_dir() and any(destino.iterdir()) and not forcar:
        logger.info("%s: já existe, pulando", dataset.pasta)
        return "ja_existia"

    raiz.mkdir(parents=True, exist_ok=True)
    zip_tmp = raiz / f"{dataset.pasta}.zip"
    requisicao = urllib.request.Request(
        URL_DOWNLOAD.format(slug=dataset.slug), headers={"Authorization": f"Bearer {token}"}
    )
    opener = urllib.request.build_opener(_RedirectSemCredencial)
    try:
        with opener.open(requisicao, timeout=300) as resposta, open(zip_tmp, "wb") as saida:
            shutil.copyfileobj(resposta, saida)
        if forcar and destino.exists():
            shutil.rmtree(destino)
        destino.mkdir(parents=True, exist_ok=True)
        n = extrair_zip_seguro(zip_tmp, destino)
    finally:
        zip_tmp.unlink(missing_ok=True)
    logger.info("%s: %d arquivos", dataset.pasta, n)
    return "baixado"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--forcar", action="store_true", help="baixa mesmo se já existir")
    parser.add_argument("--destino", type=Path, default=DATA_RAW_DIR, help="pasta de saída")
    args = parser.parse_args()

    token = ler_token()
    for dataset in DATASETS_KAGGLE:
        baixar(dataset, token, args.destino, args.forcar)


if __name__ == "__main__":
    main()
