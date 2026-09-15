"""Store the generation wizard draft with the project."""

from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("business_case_projects") as batch:
        batch.add_column(sa.Column("setup_json", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("business_case_projects") as batch:
        batch.drop_column("setup_json")
