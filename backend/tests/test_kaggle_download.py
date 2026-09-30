"""Testes do download do Kaggle que não tocam a rede."""

import urllib.request
import zipfile

import pytest

from app.pipeline import kaggle_download
from app.pipeline.kaggle_download import (
    TokenAusente,
    _RedirectSemCredencial,
    baixar,
    extrair_zip_seguro,
    ler_token,
)


def test_token_vem_da_variavel_de_ambiente(monkeypatch, tmp_path):
    monkeypatch.setenv("KAGGLE_API_TOKEN", " KGAT_teste \n")
    monkeypatch.setattr(kaggle_download, "ARQUIVO_TOKEN", tmp_path / "nao_existe")

    assert ler_token() == "KGAT_teste"


def test_token_vem_do_arquivo_se_nao_ha_variavel(monkeypatch, tmp_path):
    arquivo = tmp_path / "access_token"
    arquivo.write_text("KGAT_do_arquivo\n")
    monkeypatch.delenv("KAGGLE_API_TOKEN", raising=False)
    monkeypatch.setattr(kaggle_download, "ARQUIVO_TOKEN", arquivo)

    assert ler_token() == "KGAT_do_arquivo"


def test_sem_token_explica_como_criar(monkeypatch, tmp_path):
    monkeypatch.delenv("KAGGLE_API_TOKEN", raising=False)
    monkeypatch.setattr(kaggle_download, "ARQUIVO_TOKEN", tmp_path / "nao_existe")

    with pytest.raises(TokenAusente, match="Create Token"):
        ler_token()


def test_pasta_ja_baixada_nao_e_baixada_de_novo(tmp_path):
    """Idempotência: sem rede nenhuma, rodar de novo não faz nada."""
    dataset = kaggle_download.DATASETS_KAGGLE[0]
    (tmp_path / dataset.pasta).mkdir()
    (tmp_path / dataset.pasta / "drivers.csv").write_text("x")

    assert baixar(dataset, "token", tmp_path) == "ja_existia"


def test_zip_com_caminho_para_fora_do_destino_e_recusado(tmp_path):
    malicioso = tmp_path / "ruim.zip"
    with zipfile.ZipFile(malicioso, "w") as z:
        z.writestr("../../fora.txt", "x")

    with pytest.raises(ValueError, match="suspeito"):
        extrair_zip_seguro(malicioso, tmp_path / "destino")
    assert not (tmp_path / "fora.txt").exists()


def test_redirect_para_outro_servidor_nao_leva_o_token():
    original = urllib.request.Request(
        "https://www.kaggle.com/api/v1/datasets/download/x/y",
        headers={"Authorization": "Bearer segredo"},
    )

    novo = _RedirectSemCredencial().redirect_request(
        original, None, 302, "Found", {}, "https://storage.googleapis.com/assinado"
    )

    assert not novo.has_header("Authorization")
