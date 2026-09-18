"""Testes unitários e de integração para os mapas de pista (Contrato D4).

Testa a validação lógica e os métodos de consulta consumidos pelo Isaac.
"""

from app.config import TRACK_MAPS_DIR
from app.models.track import TrackMap
from app.pipeline.validate_track_map import validate_file, validate_track_dict


def test_official_track_maps_pass_validation():
    """Os 3 circuitos oficiais (Interlagos, Monza, Mônaco) devem passar 100% na validação D4."""
    for circuit_id in ["interlagos", "monza", "monaco"]:
        caminho = TRACK_MAPS_DIR / f"{circuit_id}.json"
        assert caminho.exists(), f"{circuit_id}.json não encontrado em {TRACK_MAPS_DIR}"
        erros = validate_file(caminho)
        assert erros == [], f"Erros encontrados em {circuit_id}.json: {erros}"


def test_validator_rejects_zone_exceeding_track_length():
    """O validador deve rejeitar zonas que ultrapassam o comprimento total da pista."""
    dados_invalidos = {
        "circuit_id": "teste",
        "length_m": 1000,
        "points": [{"x": 0, "y": 0, "distance_m": 0}, {"x": 0, "y": 0, "distance_m": 1000}],
        "zones": [{"type": "sector", "start_m": 0, "end_m": 1200, "props": {"number": 1}}],
    }
    erros = validate_track_dict(dados_invalidos)
    assert any("fora" in e for e in erros)


def test_validator_rejects_invalid_point_zone():
    """Zonas pontuais como drs_detection devem ter start_m == end_m."""
    dados_invalidos = {
        "circuit_id": "teste",
        "length_m": 1000,
        "points": [{"x": 0, "y": 0, "distance_m": 0}, {"x": 0, "y": 0, "distance_m": 1000}],
        "zones": [{"type": "drs_detection", "start_m": 100, "end_m": 150, "props": {}}],
    }
    erros = validate_track_dict(dados_invalidos)
    assert any("pontual" in e for e in erros)


def test_validator_rejects_invalid_braking_enums():
    """Frenagens com severidade ou escapatória inválidas devem ser reprovadas."""
    dados = {
        "circuit_id": "teste",
        "length_m": 1000,
        "points": [{"x": 0, "y": 0, "distance_m": 0}, {"x": 0, "y": 0, "distance_m": 1000}],
        "zones": [
            {
                "type": "braking_zone",
                "start_m": 100,
                "end_m": 200,
                "props": {"severity": "extrema", "runoff": "piscina"},
            }
        ],
    }
    erros = validate_track_dict(dados)
    assert any("severity" in e for e in erros)
    assert any("runoff" in e for e in erros)


def test_isaac_can_load_and_query_interlagos():
    """Verifica se o módulo do Isaac carrega Interlagos e responde consultas lineares."""
    track = TrackMap.load("interlagos")
    assert track.circuit_id == "interlagos"
    assert track.length_m == 4309

    # Setores
    assert track.get_active_sector(100.0) == 1
    assert track.get_active_sector(2000.0) == 2
    assert track.get_active_sector(3500.0) == 3

    # Frenagem do S do Senna (~300m)
    braking = track.get_braking_zone_at(300.0)
    assert braking is not None
    assert braking.props["severity"] == "alta"
    assert braking.props["runoff"] in ["asfalto", "brita"]

    # Reta Oposta tem DRS ativo
    assert track.is_drs_active(800.0) is True

    # Ponto no miolo não tem DRS
    assert track.is_drs_active(2000.0) is False

    # Pit lane próximo à linha de chegada
    assert track.is_in_pit_lane(4200.0) is True


def test_isaac_can_load_and_query_monza_and_monaco():
    """Verifica se o módulo do Isaac carrega Monza e Mônaco corretamente."""
    monza = TrackMap.load("monza")
    assert monza.circuit_id == "monza"
    assert monza.length_m == 5793
    assert monza.get_active_sector(500.0) == 1
    assert monza.is_drs_active(3200.0) is True

    monaco = TrackMap.load("monaco")
    assert monaco.circuit_id == "monaco"
    assert monaco.length_m == 3337
    assert monaco.get_active_sector(500.0) == 1
    # Frenagem da Nouvelle Chicane (~2050m) com muro
    braking_chicane = monaco.get_braking_zone_at(2050.0)
    assert braking_chicane is not None
    assert braking_chicane.props["runoff"] == "muro"
