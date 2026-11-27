"""Confere as rotas contra o contrato D2 publicado em `docs/openapi.json`.

API-first: o contrato foi escrito antes, e este teste quebra se uma resposta deixar
de bater com ele (campo faltando, tipo errado) ou se o modelo e o contrato divergirem.
"""

import json
import uuid
from datetime import datetime

import pytest

from app.api.races import (
    CorridaDetalhes,
    CriarCorridaRequest,
    CriarCorridaResponse,
    ResultadoDoPiloto,
    ResultadosDaCorrida,
)
from app.config import REPO_ROOT
from tests.api.test_races import GRID, _criar, _pedido

OPENAPI = json.loads((REPO_ROOT / "docs" / "openapi.json").read_text(encoding="utf-8"))
ESQUEMAS = OPENAPI["components"]["schemas"]
TIPOS = {
    "string": str, "integer": int, "number": (int, float), "boolean": bool,
    "array": list, "object": dict, "null": type(None),
}  # fmt: skip


def validar(valor, esquema, caminho="$") -> None:
    """Valida `valor` contra um esquema do OpenAPI 3.1 (o subconjunto que o contrato usa)."""
    if "$ref" in esquema:
        return validar(valor, ESQUEMAS[esquema["$ref"].split("/")[-1]], caminho)
    tipos = esquema["type"] if isinstance(esquema.get("type"), list) else [esquema.get("type")]
    if tipos != [None]:
        aceitos = tuple(
            t
            for nome in tipos
            for t in (TIPOS[nome] if isinstance(TIPOS[nome], tuple) else (TIPOS[nome],))
        )
        assert isinstance(valor, aceitos) and not (
            isinstance(valor, bool) and "boolean" not in tipos
        ), f"{caminho}: esperava {tipos}, veio {type(valor).__name__} ({valor!r})"
    if "enum" in esquema:
        assert valor in esquema["enum"], f"{caminho}: {valor!r} fora de {esquema['enum']}"
    if esquema.get("format") == "uuid":
        uuid.UUID(valor)
    if esquema.get("format") == "date-time":
        datetime.fromisoformat(valor)
    if isinstance(valor, dict):
        faltam = set(esquema.get("required", [])) - set(valor)
        assert not faltam, f"{caminho}: campos obrigatórios ausentes {sorted(faltam)}"
        for chave, sub in esquema.get("properties", {}).items():
            if chave in valor:
                validar(valor[chave], sub, f"{caminho}.{chave}")
    if isinstance(valor, list) and "items" in esquema:
        for i, item in enumerate(valor):
            validar(item, esquema["items"], f"{caminho}[{i}]")


def test_o_pedido_que_o_frontend_envia_e_valido_no_contrato_e_aceito(cliente):
    pedido = _pedido(weather="DRY", track_temp=32.0, initial_tyres={"VER": "MEDIUM"})
    validar(pedido, ESQUEMAS["CreateRaceRequest"])

    assert cliente.post("/api/races", json=pedido).status_code == 201


def test_resposta_do_post_bate_com_o_contrato(cliente):
    validar(_criar(cliente).json(), ESQUEMAS["CreateRaceResponse"])


def test_resposta_do_get_bate_com_o_contrato(cliente):
    race_id = _criar(cliente).json()["race_id"]

    validar(cliente.get(f"/api/races/{race_id}").json(), ESQUEMAS["RaceDetailsResponse"])


def test_resultados_batem_com_o_contrato(cliente):
    race_id = _criar(cliente).json()["race_id"]

    validar(cliente.get(f"/api/races/{race_id}/results").json(), ESQUEMAS["RaceResultsResponse"])


@pytest.mark.parametrize(
    "modelo, esquema",
    [
        (CriarCorridaRequest, "CreateRaceRequest"),
        (CriarCorridaResponse, "CreateRaceResponse"),
        (CorridaDetalhes, "RaceDetailsResponse"),
        (ResultadoDoPiloto, "DriverFinalResult"),
        (ResultadosDaCorrida, "RaceResultsResponse"),
    ],
)
def test_os_campos_do_modelo_sao_os_do_contrato(modelo, esquema):
    """Pega o desvio dos dois lados: campo novo no código ou campo do contrato esquecido."""
    assert set(modelo.model_fields) == set(ESQUEMAS[esquema]["properties"])


def test_o_grid_de_exemplo_do_contrato_cabe_no_grid_do_seed(cliente):
    """O exemplo da documentação tem que funcionar de verdade."""
    exemplo = ESQUEMAS["CreateRaceRequest"]["properties"]["grid"]["example"]

    assert cliente.post("/api/races", json=_pedido(grid=exemplo)).status_code == 201
    assert GRID  # o grid de teste curto continua válido
