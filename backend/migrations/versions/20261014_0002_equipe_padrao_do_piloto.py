"""equipe padrão do piloto

O grid do contrato D2 (POST /api/races) traz só códigos de piloto, mas cada inscrição
precisa de uma equipe. `drivers.team_id` guarda a equipe padrão do piloto na
temporada do seed. É nulo para quem ainda não tem uma, e a FK não apaga em cascata.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-14 22:24:16.856779
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("drivers", sa.Column("team_id", sa.Integer(), nullable=True))
    op.create_foreign_key(op.f("fk_drivers_team_id_teams"), "drivers", "teams", ["team_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint(op.f("fk_drivers_team_id_teams"), "drivers", type_="foreignkey")
    op.drop_column("drivers", "team_id")
