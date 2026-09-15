"""Add project-scoped generation idempotency keys."""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("generation_runs") as batch:
        batch.add_column(sa.Column("idempotency_key", sa.String(length=120), nullable=True))
        batch.create_unique_constraint("uq_generation_runs_project_idempotency", ["project_id", "idempotency_key"])


def downgrade() -> None:
    with op.batch_alter_table("generation_runs") as batch:
        batch.drop_constraint("uq_generation_runs_project_idempotency", type_="unique")
        batch.drop_column("idempotency_key")
