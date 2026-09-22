"""Modelos ORM do ApexSim.

Duas famílias de tabelas:

* Referência (`circuits`, `drivers`, `teams`, `tyre_compounds`): dados quase
  estáticos, carregados por seed a partir das fontes (FastF1, Jolpica, Kaggle).
* Transacionais (`setups`, `races`, `race_entries`, `lap_records`,
  `race_events`): criados a cada corrida simulada. O estado vivo da corrida
  mora na memória do motor; o banco só recebe o histórico, em lote, uma vez
  por volta (nunca a cada tick).

Decisão de projeto: o que o motor emite volta a volta (`lap_records`) e os
eventos de pista (`race_events`) são relacionais, porque é sobre eles que os
gráficos pós-corrida consultam. Já a *configuração* da corrida e do setup
(clima, grid, estratégia inicial) fica em JSONB, porque o contrato de API de
criação de corrida ainda não está no repositório e normalizar agora forçaria
uma migration a cada ajuste dele.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    Identity,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base

# Estados possíveis de uma corrida. Ficam em CHECK (e não em ENUM nativo do
# PostgreSQL) porque ALTER TYPE ... ADD VALUE é chato de reverter em migration.
STATUS_DA_CORRIDA = ("configured", "running", "finished", "aborted")


# ---------------------------------------------------------------------------
# Tabelas de referência
# ---------------------------------------------------------------------------


class Circuit(Base):
    """Um circuito. `id` é o slug do contrato D3/D4 (ex.: "interlagos")."""

    __tablename__ = "circuits"
    __table_args__ = (CheckConstraint("length_m > 0", name="length_positive"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    country: Mapped[str | None] = mapped_column(String(60))
    # Comprimento oficial (FIA), o mesmo `length_m` dos JSONs de circuits/.
    length_m: Mapped[int] = mapped_column(Integer)


class Team(Base):
    """Uma equipe. Quem corre por qual equipe em cada prova está em `race_entries`."""

    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)


class Driver(Base):
    """Um piloto.

    Chave substituta (`id`) em vez do código FIA como PK: nas fontes históricas
    o código pode se repetir (Michael e Mick Schumacher são "MSC") e o nome do
    piloto diverge entre datasets, o que a reconciliação da semana 4 precisa
    poder corrigir sem reescrever chaves estrangeiras.
    """

    __tablename__ = "drivers"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    # Código FIA de 3 letras ("HAM"): é o `driver_id` que o motor emite.
    code: Mapped[str] = mapped_column(String(3), unique=True)
    full_name: Mapped[str] = mapped_column(String(100))


class TyreCompound(Base):
    """Composto de pneu. `code` espelha os nomes de `TyreCompound` em sim/state.py."""

    __tablename__ = "tyre_compounds"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name_pt: Mapped[str] = mapped_column(String(30))


# ---------------------------------------------------------------------------
# Tabelas transacionais
# ---------------------------------------------------------------------------


class Setup(Base):
    """Setup/estratégia inicial salva pelo usuário (CRUD via REST)."""

    __tablename__ = "setups"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    # Nulo = setup genérico, válido para qualquer circuito.
    circuit_id: Mapped[str | None] = mapped_column(ForeignKey("circuits.id"))
    # Compostos, janelas de pit stop e combustível inicial, como o usuário enviou.
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Race(Base):
    """Uma corrida simulada."""

    __tablename__ = "races"
    __table_args__ = (
        CheckConstraint("total_laps > 0", name="total_laps_positive"),
        CheckConstraint(
            "status IN ('" + "', '".join(STATUS_DA_CORRIDA) + "')",
            name="status_valid",
        ),
    )

    # UUID, igual ao `race_id` do contrato D2 (WebSocket e REST). O default do
    # Python deixa a API gerar o id antes de gravar; o do banco cobre SQL cru.
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    circuit_id: Mapped[str] = mapped_column(ForeignKey("circuits.id"))
    # Se o setup for apagado a corrida continua existindo: o que valeu foi o
    # snapshot em `config`.
    setup_id: Mapped[int | None] = mapped_column(ForeignKey("setups.id", ondelete="SET NULL"))
    # Mesma seed produz exatamente a mesma corrida (requisito do motor).
    seed: Mapped[int] = mapped_column(BigInteger)
    total_laps: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        String(16), server_default=text("'configured'"), default="configured"
    )
    # Configuração completa como recebida: clima, grid, estratégia inicial.
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    entries: Mapped[list["RaceEntry"]] = relationship(
        back_populates="race", cascade="all, delete-orphan", passive_deletes=True
    )


class RaceEntry(Base):
    """Um piloto inscrito numa corrida, com a equipe e a posição de largada.

    Guarda a equipe *na prova* (pilotos trocam de equipe entre temporadas) e é
    o ponto de ligação das voltas e dos eventos: um `lap_record` só pode existir
    para um piloto que de fato largou naquela corrida.
    """

    __tablename__ = "race_entries"
    __table_args__ = (
        UniqueConstraint("race_id", "driver_id", name="uq_race_entries_race_driver"),
        UniqueConstraint("race_id", "grid_position", name="uq_race_entries_race_grid"),
        CheckConstraint("grid_position >= 1", name="grid_position_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    race_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("races.id", ondelete="CASCADE"))
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    grid_position: Mapped[int] = mapped_column(Integer)

    race: Mapped[Race] = relationship(back_populates="entries")
    driver: Mapped[Driver] = relationship()
    team: Mapped[Team] = relationship()


class LapRecord(Base):
    """Resultado de uma volta de um piloto. Espelha `LapResult` de sim/state.py."""

    __tablename__ = "lap_records"
    __table_args__ = (
        UniqueConstraint("entry_id", "lap_number", name="uq_lap_records_entry_lap"),
        CheckConstraint("lap_number >= 1", name="lap_number_positive"),
        CheckConstraint("lap_time_s > 0", name="lap_time_positive"),
        CheckConstraint("position >= 1", name="position_positive"),
        CheckConstraint("gap_to_leader_s >= 0", name="gap_to_leader_nonneg"),
        CheckConstraint("tyre_age_laps >= 0", name="tyre_age_nonneg"),
        CheckConstraint("fuel_load_kg >= 0", name="fuel_load_nonneg"),
        # LapResult documenta pit_time como "None se pit_stop for False".
        CheckConstraint("pit_stop OR pit_time_s IS NULL", name="pit_time_only_with_stop"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("race_entries.id", ondelete="CASCADE"))
    lap_number: Mapped[int] = mapped_column(Integer)
    lap_time_s: Mapped[float] = mapped_column(Double)
    position: Mapped[int] = mapped_column(Integer)
    gap_to_leader_s: Mapped[float] = mapped_column(Double)
    # Nulo para o líder (não há carro à frente).
    gap_to_ahead_s: Mapped[float | None] = mapped_column(Double)
    tyre_compound_code: Mapped[str] = mapped_column(ForeignKey("tyre_compounds.code"))
    tyre_age_laps: Mapped[int] = mapped_column(Integer)
    fuel_load_kg: Mapped[float] = mapped_column(Double)
    pit_stop: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), default=False)
    pit_time_s: Mapped[float | None] = mapped_column(Double)


class RaceEvent(Base):
    """Evento de pista: acidente, Safety Car/VSC, bandeira, clima, penalidade.

    `event_type` é texto livre validado na camada de repositório, e não um CHECK:
    o gerador de eventos do Isaac ainda está sendo desenhado (M3) e cada tipo novo
    não deveria exigir uma migration. Os detalhes específicos de cada tipo (zona do
    acidente, duração do Safety Car...) ficam em `payload`.
    """

    __tablename__ = "race_events"
    __table_args__ = (CheckConstraint("lap_number >= 0", name="lap_number_nonneg"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    race_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("races.id", ondelete="CASCADE"), index=True
    )
    # Volta 0 = largada. Nulo em `entry_id` quando o evento é global (ex.: chuva).
    lap_number: Mapped[int] = mapped_column(Integer)
    entry_id: Mapped[int | None] = mapped_column(ForeignKey("race_entries.id", ondelete="SET NULL"))
    event_type: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
