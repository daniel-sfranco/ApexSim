"""Testes de integridade do schema: o banco tem que recusar dado incoerente.

A ideia é que o motor de simulação (que persiste em lote a cada volta) nunca
consiga gravar silenciosamente uma volta duplicada, um pit_time sem pit stop ou
um composto que não existe. O erro tem que estourar na hora, alto.
"""

import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.models import (
    Circuit,
    Driver,
    LapRecord,
    Race,
    RaceEntry,
    RaceEvent,
    Setup,
    Team,
    TyreCompound,
)


@pytest.fixture
def entrada(session: Session) -> RaceEntry:
    """Uma corrida mínima válida com um piloto inscrito."""
    circuito = Circuit(id="monza", name="Autodromo Nazionale Monza", length_m=5793)
    piloto = Driver(code="HAM", full_name="Lewis Hamilton")
    equipe = Team(name="Equipe Teste")
    session.add_all([circuito, piloto, equipe, TyreCompound(code="SOFT", name_pt="Macio")])
    session.flush()

    corrida = Race(circuit_id=circuito.id, seed=42, total_laps=50, config={})
    session.add(corrida)
    session.flush()

    entrada = RaceEntry(race_id=corrida.id, driver_id=piloto.id, team_id=equipe.id, grid_position=1)
    session.add(entrada)
    session.flush()
    return entrada


def _volta(entrada: RaceEntry, numero: int = 1, **campos) -> LapRecord:
    """Volta válida por padrão; cada teste sobrescreve só o campo que quer quebrar."""
    valores = {
        "entry_id": entrada.id,
        "lap_number": numero,
        "lap_time_s": 90.5,
        "position": 1,
        "gap_to_leader_s": 0.0,
        "gap_to_ahead_s": None,
        "tyre_compound_code": "SOFT",
        "tyre_age_laps": numero,
        "fuel_load_kg": 100.0,
    }
    valores.update(campos)
    return LapRecord(**valores)


def _recusa(session: Session, objeto) -> None:
    """Afirma que o banco rejeita `objeto`, sem deixar a sessão inutilizada."""
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(objeto)
            session.flush()


# --- o caminho feliz --------------------------------------------------------


def test_volta_valida_e_gravada_com_defaults(session, entrada):
    session.add(_volta(entrada))
    session.flush()

    volta = session.scalars(select(LapRecord)).one()
    assert volta.pit_stop is False
    assert volta.pit_time_s is None
    assert volta.gap_to_ahead_s is None


def test_corrida_nasce_configurada_e_com_data(session, entrada):
    corrida = session.get(Race, entrada.race_id)
    session.refresh(corrida)

    assert corrida.status == "configured"
    assert corrida.created_at is not None
    assert corrida.finished_at is None


def test_evento_global_nao_exige_piloto_e_payload_padrao_e_vazio(session, entrada):
    session.add(RaceEvent(race_id=entrada.race_id, lap_number=12, event_type="weather_change"))
    session.flush()

    evento = session.scalars(select(RaceEvent)).one()
    session.refresh(evento)
    assert evento.entry_id is None
    assert evento.payload == {}


def test_corrida_tem_id_uuid_gerado_pela_aplicacao_e_pelo_banco(session, entrada):
    """O `race_id` do contrato D2 é UUID: a API gera antes de gravar, e o SQL cru também."""
    assert isinstance(entrada.race_id, uuid.UUID)

    id_do_banco = session.scalar(
        text(
            "INSERT INTO races (circuit_id, seed, total_laps, config) "
            "VALUES ('monza', 1, 10, '{}') RETURNING id"
        )
    )
    assert isinstance(id_do_banco, uuid.UUID)


# --- o banco recusa dado incoerente ----------------------------------------


def test_volta_duplicada_e_rejeitada(session, entrada):
    session.add(_volta(entrada, numero=3))
    session.flush()

    _recusa(session, _volta(entrada, numero=3))


def test_pit_time_sem_pit_stop_e_rejeitado(session, entrada):
    _recusa(session, _volta(entrada, pit_stop=False, pit_time_s=22.4))


def test_pit_time_com_pit_stop_e_aceito(session, entrada):
    session.add(_volta(entrada, pit_stop=True, pit_time_s=22.4))
    session.flush()


@pytest.mark.parametrize(
    "campo, valor",
    [
        ("lap_time_s", 0.0),
        ("lap_time_s", -1.0),
        ("lap_number", 0),
        ("position", 0),
        ("gap_to_leader_s", -0.1),
        ("tyre_age_laps", -1),
        ("fuel_load_kg", -0.5),
    ],
)
def test_valores_fora_da_faixa_sao_rejeitados(session, entrada, campo, valor):
    _recusa(session, _volta(entrada, **{campo: valor}))


def test_composto_inexistente_e_rejeitado(session, entrada):
    _recusa(session, _volta(entrada, tyre_compound_code="PLASTICO"))


def test_status_de_corrida_invalido_e_rejeitado(session, entrada):
    _recusa(session, Race(circuit_id="monza", seed=1, total_laps=10, config={}, status="pausada"))


def test_corrida_sem_voltas_e_rejeitada(session, entrada):
    _recusa(session, Race(circuit_id="monza", seed=1, total_laps=0, config={}))


def test_dois_pilotos_na_mesma_posicao_do_grid_sao_rejeitados(session, entrada):
    outro = Driver(code="VER", full_name="Max Verstappen")
    session.add(outro)
    session.flush()

    _recusa(
        session,
        RaceEntry(
            race_id=entrada.race_id,
            driver_id=outro.id,
            team_id=entrada.team_id,
            grid_position=entrada.grid_position,
        ),
    )


def test_mesmo_piloto_duas_vezes_na_corrida_e_rejeitado(session, entrada):
    _recusa(
        session,
        RaceEntry(
            race_id=entrada.race_id,
            driver_id=entrada.driver_id,
            team_id=entrada.team_id,
            grid_position=2,
        ),
    )


# --- o que acontece ao apagar ----------------------------------------------


def test_apagar_corrida_leva_entradas_voltas_e_eventos_junto(session, entrada):
    session.add(_volta(entrada))
    session.add(RaceEvent(race_id=entrada.race_id, lap_number=1, event_type="safety_car"))
    session.flush()

    session.delete(session.get(Race, entrada.race_id))
    session.flush()

    for modelo in (RaceEntry, LapRecord, RaceEvent):
        assert session.scalar(select(func.count()).select_from(modelo)) == 0


def test_apagar_setup_preserva_a_corrida(session, entrada):
    """A corrida guarda um snapshot da config; o setup salvo é só conveniência."""
    setup = Setup(name="Duas paradas", config={"paradas": 2})
    session.add(setup)
    session.flush()
    corrida = session.get(Race, entrada.race_id)
    corrida.setup_id = setup.id
    session.flush()

    session.delete(setup)
    session.flush()
    session.refresh(corrida)

    assert corrida.setup_id is None
