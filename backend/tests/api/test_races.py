"""Testes das rotas de corrida: criar, consultar e classificar."""

import uuid

import pytest
from sqlalchemy import func, select

from db.models import Circuit, Race, RaceEntry
from db.repositorio import (
    EventoDeCorrida,
    gravar_eventos,
    gravar_voltas,
    mapa_entradas,
)
from sim.state import LapResult, TyreCompound

GRID = ["VER", "NOR", "LEC", "PIA"]


def _pedido(**mudancas) -> dict:
    corpo = {"circuit_id": "monza", "total_laps": 53, "seed": 42, "grid": GRID}
    corpo.update(mudancas)
    return corpo


def _criar(cliente, **mudancas):
    return cliente.post("/api/races", json=_pedido(**mudancas))


def _contar(session, modelo) -> int:
    return session.scalar(select(func.count()).select_from(modelo))


# --- POST /api/races ----------------------------------------------------------


def test_criar_devolve_201_com_o_contrato_e_grava_a_corrida(cliente, session):
    resposta = _criar(cliente, weather="DAMP", track_temp=28.5)

    assert resposta.status_code == 201
    corpo = resposta.json()
    race_id = uuid.UUID(corpo["race_id"])
    assert corpo["ws_url"] == f"/ws/races/{race_id}"
    assert (corpo["circuit_id"], corpo["total_laps"], corpo["seed"]) == ("monza", 53, 42)
    assert corpo["status"] == "configured"
    corrida = session.get(Race, race_id)
    assert corrida.config["weather"] == "DAMP" and corrida.config["track_temp"] == 28.5


def test_o_grid_vira_inscricoes_na_ordem_com_a_equipe_padrao(cliente, session):
    race_id = uuid.UUID(_criar(cliente).json()["race_id"])

    inscritos = session.scalars(
        select(RaceEntry).where(RaceEntry.race_id == race_id).order_by(RaceEntry.grid_position)
    ).all()

    assert [(i.grid_position, i.driver.code, i.team.name) for i in inscritos] == [
        (1, "VER", "Red Bull Racing"),
        (2, "NOR", "McLaren"),
        (3, "LEC", "Ferrari"),
        (4, "PIA", "McLaren"),
    ]


def test_valores_padrao_do_contrato(cliente, session):
    resposta = cliente.post("/api/races", json={"circuit_id": "interlagos", "total_laps": 10,
                                                "seed": 1, "grid": GRID})  # fmt: skip

    config = session.get(Race, uuid.UUID(resposta.json()["race_id"])).config

    assert (config["weather"], config["track_temp"], config["initial_tyres"]) == ("DRY", 32.0, {})


def test_pneus_iniciais_ficam_na_config(cliente, session):
    resposta = _criar(cliente, initial_tyres={"VER": "SOFT", "NOR": "HARD"})

    config = session.get(Race, uuid.UUID(resposta.json()["race_id"])).config

    assert config["initial_tyres"] == {"VER": "SOFT", "NOR": "HARD"}


def test_circuito_desconhecido_e_404(cliente, session):
    resposta = _criar(cliente, circuit_id="zandvoort")

    assert resposta.status_code == 404
    assert _contar(session, Race) == 0


def test_circuito_sem_mapa_de_pista_e_404(cliente, session):
    session.add(Circuit(id="spa", name="Spa-Francorchamps", length_m=7004))
    session.flush()

    resposta = _criar(cliente, circuit_id="spa")

    assert resposta.status_code == 404 and "mapa" in resposta.json()["detail"]
    assert _contar(session, Race) == 0


@pytest.mark.parametrize("id_ruim", ["../../etc/passwd", "MONZA", "monza.json", "a b"])
def test_circuit_id_fora_do_padrao_nem_chega_ao_banco(cliente, id_ruim):
    """O id vira nome de arquivo em TrackMap.load: só slugs simples passam."""
    assert _criar(cliente, circuit_id=id_ruim).status_code == 422


def test_sem_grid_e_422_explicando(cliente, session):
    corpo = _pedido()
    del corpo["grid"]

    resposta = cliente.post("/api/races", json=corpo)

    assert resposta.status_code == 422 and "grid" in resposta.json()["detail"]
    assert _contar(session, Race) == 0


@pytest.mark.parametrize(
    "grid",
    [[], ["VER", "VER"], [f"P{i:02d}" for i in range(21)]],
    ids=["vazio", "repetido", "mais de 20"],
)
def test_grid_invalido_e_422(cliente, session, grid):
    assert _criar(cliente, grid=grid).status_code == 422
    assert _contar(session, Race) == 0


def test_piloto_desconhecido_e_422_listando_o_codigo(cliente, session):
    resposta = _criar(cliente, grid=["VER", "XXX", "YYY"])

    assert resposta.status_code == 422
    assert "XXX" in resposta.json()["detail"] and "YYY" in resposta.json()["detail"]
    assert _contar(session, Race) == 0


def test_pneus_iniciais_de_piloto_fora_do_grid_e_422(cliente):
    resposta = _criar(cliente, initial_tyres={"HAM": "SOFT"})

    assert resposta.status_code == 422 and "HAM" in resposta.json()["detail"]


@pytest.mark.parametrize(
    "mudanca",
    [{"total_laps": 0}, {"total_laps": 101}, {"weather": "SNOW"}, {"initial_tyres": {"VER": "X"}}],
)
def test_valores_fora_do_contrato_sao_422(cliente, mudanca):
    assert _criar(cliente, **mudanca).status_code == 422


# --- GET /api/races/{id} --------------------------------------------------------


def _volta(codigo, numero, tempo, parou=False) -> LapResult:
    return LapResult(
        driver_id=codigo, lap_number=numero, lap_time=tempo, position=1, gap_to_leader=0.0,
        gap_to_ahead=None, tyre_compound=TyreCompound.SOFT, tyre_age=numero, fuel_load=90.0,
        pit_stop=parou, pit_time=22.0 if parou else None,
    )  # fmt: skip


def test_detalhes_antes_da_largada(cliente):
    race_id = _criar(cliente).json()["race_id"]

    corpo = cliente.get(f"/api/races/{race_id}").json()

    assert corpo["current_lap"] == 0 and corpo["status"] == "configured"
    assert corpo["total_laps"] == 53 and corpo["circuit_id"] == "monza"
    assert corpo["created_at"]


def test_volta_atual_e_a_maior_volta_gravada(cliente, session):
    race_id = uuid.UUID(_criar(cliente).json()["race_id"])
    mapa = mapa_entradas(session, race_id)
    for numero in (1, 2, 3):
        gravar_voltas(session, mapa, [_volta(c, numero, 80.0) for c in GRID])

    assert cliente.get(f"/api/races/{race_id}").json()["current_lap"] == 3


def test_corrida_inexistente_e_404_e_id_invalido_e_422(cliente):
    assert cliente.get(f"/api/races/{uuid.uuid4()}").status_code == 404
    assert cliente.get("/api/races/nao-e-uuid").status_code == 422
    assert cliente.get(f"/api/races/{uuid.uuid4()}/results").status_code == 404


# --- GET /api/races/{id}/results --------------------------------------------------


@pytest.fixture
def corrida_terminada(cliente, session):
    """VER 3x80 (parou na volta 2); NOR 3x81; PIA 79, 79, 100; LEC abandonou na volta 3."""
    race_id = uuid.UUID(_criar(cliente).json()["race_id"])
    mapa = mapa_entradas(session, race_id)
    tempos = {"VER": [80, 80, 80], "NOR": [81, 81, 81], "PIA": [79, 79, 100], "LEC": [82, 82]}
    for numero in (1, 2, 3):
        gravar_voltas(
            session, mapa,
            [_volta(c, numero, t[numero - 1], parou=(c == "VER" and numero == 2))
             for c, t in tempos.items() if numero <= len(t)],
        )  # fmt: skip
    gravar_eventos(session, race_id, mapa, [EventoDeCorrida(3, "RETIREMENT", "LEC")])
    return race_id


def test_classificacao_ordena_por_voltas_e_depois_por_tempo(cliente, corrida_terminada):
    corpo = cliente.get(f"/api/races/{corrida_terminada}/results").json()

    ordem = [(r["position"], r["driver_id"]) for r in corpo["classification"]]

    # LEC tem tempo total menor (164 s), mas só 2 voltas: fica por último
    assert ordem == [(1, "VER"), (2, "NOR"), (3, "PIA"), (4, "LEC")]


def test_totais_paradas_volta_mais_rapida_e_abandono(cliente, corrida_terminada):
    corpo = cliente.get(f"/api/races/{corrida_terminada}/results").json()
    por_piloto = {r["driver_id"]: r for r in corpo["classification"]}

    assert por_piloto["VER"]["total_race_time"] == 240 and por_piloto["VER"]["pit_stops_made"] == 1
    assert por_piloto["PIA"]["fastest_lap"] == 79 and por_piloto["NOR"]["pit_stops_made"] == 0
    assert por_piloto["LEC"]["is_retired"] is True and por_piloto["VER"]["is_retired"] is False
    assert (
        por_piloto["VER"]["name"] == "Max Verstappen"
        and por_piloto["VER"]["team"] == "Red Bull Racing"
    )


def test_gap_e_para_o_lider_no_mesmo_numero_de_voltas(cliente, corrida_terminada):
    corpo = cliente.get(f"/api/races/{corrida_terminada}/results").json()
    gaps = {r["driver_id"]: r["gap_to_leader"] for r in corpo["classification"]}

    # LEC completou 2 voltas (164 s); o líder levou 160 s nas 2 primeiras: 4 s de diferença
    assert gaps == {"VER": 0, "NOR": 3, "PIA": 18, "LEC": 4}


def test_resultados_antes_da_largada_seguem_a_ordem_do_grid(cliente):
    race_id = _criar(cliente).json()["race_id"]

    corpo = cliente.get(f"/api/races/{race_id}/results").json()

    assert [r["driver_id"] for r in corpo["classification"]] == GRID
    assert all(
        r["total_race_time"] == 0 and r["fastest_lap"] is None for r in corpo["classification"]
    )
