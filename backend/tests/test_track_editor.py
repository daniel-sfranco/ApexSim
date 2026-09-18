"""Testes de integração da ferramenta de anotação de pista (Track Editor)."""

from fastapi.testclient import TestClient

from app.config import CIRCUITS_DIR, TRACK_EDITOR_DIR
from app.main import app

client = TestClient(app)


def test_track_editor_route_responds_200():
    """A rota /admin/track-editor deve responder 200 e entregar o HTML do editor."""
    resposta = client.get("/admin/track-editor/")
    assert resposta.status_code == 200
    assert "<title>ApexSim — Editor de Pistas" in resposta.text
    assert 'id="trackCanvas"' in resposta.text
    assert 'id="timelineCanvas"' in resposta.text


def test_track_editor_static_files_exist():
    """Os arquivos JS e CSS essenciais do editor devem existir e estar acessíveis."""
    assert (TRACK_EDITOR_DIR / "index.html").exists()
    assert (TRACK_EDITOR_DIR / "app.js").exists()
    assert (TRACK_EDITOR_DIR / "styles.css").exists()
    assert (TRACK_EDITOR_DIR / "circuits_data.js").exists()

    res_js = client.get("/admin/track-editor/app.js")
    assert res_js.status_code == 200

    res_css = client.get("/admin/track-editor/styles.css")
    assert res_css.status_code == 200


def test_circuits_route_serves_json():
    """A rota /circuits deve servir a geometria D3 dos circuitos."""
    for circuit_id in ["interlagos", "monza", "monaco"]:
        arquivo = CIRCUITS_DIR / f"{circuit_id}.json"
        if arquivo.exists():
            resposta = client.get(f"/circuits/{circuit_id}.json")
            assert resposta.status_code == 200
            dados = resposta.json()
            assert dados["circuit_id"] == circuit_id
            assert "points" in dados
            assert len(dados["points"]) >= 250


def test_save_and_get_track_map_api():
    """A API deve salvar e recuperar mapas semânticos em track_maps/."""
    payload = {
        "circuit_id": "test_circuit",
        "length_m": 4309,
        "points": [{"x": 0.0, "y": 0.0, "distance_m": 0.0}],
        "zones": [{"type": "sector", "start_m": 0, "end_m": 1200, "props": {"number": 1}}],
    }
    # Salvar
    resp_post = client.post("/api/track-maps/test_circuit", json=payload)
    assert resp_post.status_code == 200
    assert resp_post.json()["status"] == "saved"

    # Recuperar
    resp_get = client.get("/api/track-maps/test_circuit")
    assert resp_get.status_code == 200
    assert resp_get.json()["circuit_id"] == "test_circuit"
    assert len(resp_get.json()["zones"]) == 1
