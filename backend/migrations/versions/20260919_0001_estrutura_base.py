"""estrutura base

Cria as tabelas de referência (circuits, drivers, teams, tyre_compounds) e as
transacionais (setups, races, race_entries, lap_records, race_events). Não
insere dados: o seed idempotente é entrega da semana 5.

Revision ID: 0001
Revises:
Create Date: 2026-09-19 00:10:25.702413
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "circuits",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("country", sa.String(length=60), nullable=True),
        sa.Column("length_m", sa.Integer(), nullable=False),
        sa.CheckConstraint("length_m > 0", name=op.f("ck_circuits_length_positive")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_circuits")),
    )
    op.create_table(
        "drivers",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("code", sa.String(length=3), nullable=False),
        sa.Column("full_name", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_drivers")),
        sa.UniqueConstraint("code", name=op.f("uq_drivers_code")),
    )
    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_teams")),
        sa.UniqueConstraint("name", name=op.f("uq_teams_name")),
    )
    op.create_table(
        "tyre_compounds",
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("name_pt", sa.String(length=30), nullable=False),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_tyre_compounds")),
    )
    op.create_table(
        "setups",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("circuit_id", sa.String(length=32), nullable=True),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["circuit_id"], ["circuits.id"], name=op.f("fk_setups_circuit_id_circuits")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_setups")),
    )
    op.create_table(
        "races",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("circuit_id", sa.String(length=32), nullable=False),
        sa.Column("setup_id", sa.Integer(), nullable=True),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column("total_laps", sa.Integer(), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'configured'"), nullable=False
        ),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('configured', 'running', 'finished', 'aborted')",
            name=op.f("ck_races_status_valid"),
        ),
        sa.CheckConstraint("total_laps > 0", name=op.f("ck_races_total_laps_positive")),
        sa.ForeignKeyConstraint(
            ["circuit_id"], ["circuits.id"], name=op.f("fk_races_circuit_id_circuits")
        ),
        sa.ForeignKeyConstraint(
            ["setup_id"], ["setups.id"], name=op.f("fk_races_setup_id_setups"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_races")),
    )
    op.create_table(
        "race_entries",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("race_id", sa.Integer(), nullable=False),
        sa.Column("driver_id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("grid_position", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "grid_position >= 1", name=op.f("ck_race_entries_grid_position_positive")
        ),
        sa.ForeignKeyConstraint(
            ["driver_id"], ["drivers.id"], name=op.f("fk_race_entries_driver_id_drivers")
        ),
        sa.ForeignKeyConstraint(
            ["race_id"],
            ["races.id"],
            name=op.f("fk_race_entries_race_id_races"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name=op.f("fk_race_entries_team_id_teams")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_race_entries")),
        sa.UniqueConstraint("race_id", "driver_id", name="uq_race_entries_race_driver"),
        sa.UniqueConstraint("race_id", "grid_position", name="uq_race_entries_race_grid"),
    )
    op.create_table(
        "lap_records",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("entry_id", sa.Integer(), nullable=False),
        sa.Column("lap_number", sa.Integer(), nullable=False),
        sa.Column("lap_time_s", sa.Double(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("gap_to_leader_s", sa.Double(), nullable=False),
        sa.Column("gap_to_ahead_s", sa.Double(), nullable=True),
        sa.Column("tyre_compound_code", sa.String(length=16), nullable=False),
        sa.Column("tyre_age_laps", sa.Integer(), nullable=False),
        sa.Column("fuel_load_kg", sa.Double(), nullable=False),
        sa.Column("pit_stop", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("pit_time_s", sa.Double(), nullable=True),
        sa.CheckConstraint("fuel_load_kg >= 0", name=op.f("ck_lap_records_fuel_load_nonneg")),
        sa.CheckConstraint(
            "gap_to_leader_s >= 0", name=op.f("ck_lap_records_gap_to_leader_nonneg")
        ),
        sa.CheckConstraint("lap_number >= 1", name=op.f("ck_lap_records_lap_number_positive")),
        sa.CheckConstraint("lap_time_s > 0", name=op.f("ck_lap_records_lap_time_positive")),
        sa.CheckConstraint(
            "pit_stop OR pit_time_s IS NULL", name=op.f("ck_lap_records_pit_time_only_with_stop")
        ),
        sa.CheckConstraint("position >= 1", name=op.f("ck_lap_records_position_positive")),
        sa.CheckConstraint("tyre_age_laps >= 0", name=op.f("ck_lap_records_tyre_age_nonneg")),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            ["race_entries.id"],
            name=op.f("fk_lap_records_entry_id_race_entries"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tyre_compound_code"],
            ["tyre_compounds.code"],
            name=op.f("fk_lap_records_tyre_compound_code_tyre_compounds"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lap_records")),
        sa.UniqueConstraint("entry_id", "lap_number", name="uq_lap_records_entry_lap"),
    )
    op.create_table(
        "race_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("race_id", sa.Integer(), nullable=False),
        sa.Column("lap_number", sa.Integer(), nullable=False),
        sa.Column("entry_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("lap_number >= 0", name=op.f("ck_race_events_lap_number_nonneg")),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            ["race_entries.id"],
            name=op.f("fk_race_events_entry_id_race_entries"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["race_id"], ["races.id"], name=op.f("fk_race_events_race_id_races"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_race_events")),
    )
    op.create_index(op.f("ix_race_events_race_id"), "race_events", ["race_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_race_events_race_id"), table_name="race_events")
    op.drop_table("race_events")
    op.drop_table("lap_records")
    op.drop_table("race_entries")
    op.drop_table("races")
    op.drop_table("setups")
    op.drop_table("tyre_compounds")
    op.drop_table("teams")
    op.drop_table("drivers")
    op.drop_table("circuits")
