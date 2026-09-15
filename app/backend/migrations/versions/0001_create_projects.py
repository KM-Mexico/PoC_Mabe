"""Create business case projects."""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "business_case_projects",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("organization", sa.String(length=120), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("horizon_years", sa.Integer(), nullable=False),
        sa.Column("discount_rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("horizon_years BETWEEN 1 AND 10", name="ck_project_horizon"),
        sa.CheckConstraint("discount_rate BETWEEN 0 AND 100", name="ck_project_discount_rate"),
    )
    op.create_index("ix_projects_updated_at", "business_case_projects", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_projects_updated_at", table_name="business_case_projects")
    op.drop_table("business_case_projects")

