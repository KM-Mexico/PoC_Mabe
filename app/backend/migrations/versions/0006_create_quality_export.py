"""Create historical quality validations, findings and exports."""

from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quality_validations",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("version_id", sa.String(36), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False), sa.Column("rubric_version", sa.String(40), nullable=False),
        sa.Column("prompt_version", sa.String(40), nullable=False), sa.Column("provider_model", sa.String(160), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False), sa.Column("dimension_scores_json", sa.Text(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["version_id"], ["business_case_versions.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_quality_validations_version_created", "quality_validations", ["version_id", "created_at"])
    op.create_table(
        "quality_findings",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("validation_id", sa.String(36), nullable=False),
        sa.Column("dimension", sa.String(80), nullable=False), sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("section_id", sa.String(64)), sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False), sa.Column("deterministic", sa.Boolean(), nullable=False),
        sa.Column("comment_id", sa.String(36)),
        sa.ForeignKeyConstraint(["validation_id"], ["quality_validations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["comment_id"], ["review_comments.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_quality_findings_validation_severity", "quality_findings", ["validation_id", "severity"])
    op.create_table(
        "export_records",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("version_id", sa.String(36), nullable=False),
        sa.Column("format", sa.String(16), nullable=False), sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["version_id"], ["business_case_versions.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_export_records_version_created", "export_records", ["version_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_export_records_version_created", table_name="export_records")
    op.drop_table("export_records")
    op.drop_index("ix_quality_findings_validation_severity", table_name="quality_findings")
    op.drop_table("quality_findings")
    op.drop_index("ix_quality_validations_version_created", table_name="quality_validations")
    op.drop_table("quality_validations")
