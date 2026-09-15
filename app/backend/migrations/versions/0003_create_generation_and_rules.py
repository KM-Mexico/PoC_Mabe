"""Create generation versions, rule versions and quality snapshots."""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("rule_definitions", sa.Column("id", sa.String(36), primary_key=True), sa.Column("section_id", sa.String(64), nullable=False, unique=True), sa.Column("title", sa.String(160), nullable=False), sa.Column("ordinal", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("rule_versions", sa.Column("id", sa.String(36), primary_key=True), sa.Column("definition_id", sa.String(36), nullable=False), sa.Column("version_number", sa.Integer(), nullable=False), sa.Column("markdown", sa.Text(), nullable=False), sa.Column("status", sa.String(16), nullable=False), sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("actor", sa.String(120), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("published_at", sa.DateTime(timezone=True)), sa.ForeignKeyConstraint(["definition_id"], ["rule_definitions.id"], ondelete="CASCADE"), sa.UniqueConstraint("definition_id", "version_number", name="uq_rule_versions_definition_number"))
    op.create_index("ix_rule_versions_definition_status", "rule_versions", ["definition_id", "status"])
    op.create_table("business_case_versions", sa.Column("id", sa.String(36), primary_key=True), sa.Column("project_id", sa.String(36), nullable=False), sa.Column("version_number", sa.Integer(), nullable=False), sa.Column("status", sa.String(20), nullable=False), sa.Column("content_json", sa.Text(), nullable=False), sa.Column("input_snapshot_json", sa.Text(), nullable=False), sa.Column("rules_snapshot_json", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.ForeignKeyConstraint(["project_id"], ["business_case_projects.id"], ondelete="CASCADE"), sa.UniqueConstraint("project_id", "version_number", name="uq_case_versions_project_number"))
    op.create_table("financial_scenarios", sa.Column("id", sa.String(36), primary_key=True), sa.Column("version_id", sa.String(36), nullable=False), sa.Column("name", sa.String(32), nullable=False), sa.Column("inputs_json", sa.Text(), nullable=False), sa.Column("metrics_json", sa.Text(), nullable=False), sa.ForeignKeyConstraint(["version_id"], ["business_case_versions.id"], ondelete="CASCADE"))
    op.create_table("quality_reports", sa.Column("id", sa.String(36), primary_key=True), sa.Column("version_id", sa.String(36), nullable=False, unique=True), sa.Column("score", sa.Integer(), nullable=False), sa.Column("findings_json", sa.Text(), nullable=False), sa.Column("compliance_json", sa.Text(), nullable=False), sa.ForeignKeyConstraint(["version_id"], ["business_case_versions.id"], ondelete="CASCADE"))
    op.create_table("citation_snapshots", sa.Column("id", sa.String(36), primary_key=True), sa.Column("version_id", sa.String(36), nullable=False), sa.Column("document_id", sa.String(36)), sa.Column("chunk_id", sa.String(36)), sa.Column("document_name", sa.String(180), nullable=False), sa.Column("locator", sa.String(160), nullable=False), sa.Column("excerpt", sa.Text(), nullable=False), sa.ForeignKeyConstraint(["version_id"], ["business_case_versions.id"], ondelete="CASCADE"))
    op.create_table("assumptions", sa.Column("id", sa.String(36), primary_key=True), sa.Column("version_id", sa.String(36), nullable=False), sa.Column("section_id", sa.String(64), nullable=False), sa.Column("text", sa.Text(), nullable=False), sa.Column("impact", sa.Text(), nullable=False), sa.Column("status", sa.String(20), nullable=False), sa.ForeignKeyConstraint(["version_id"], ["business_case_versions.id"], ondelete="CASCADE"))
    op.create_table("generation_runs", sa.Column("id", sa.String(36), primary_key=True), sa.Column("project_id", sa.String(36), nullable=False), sa.Column("status", sa.String(20), nullable=False), sa.Column("progress", sa.Integer(), nullable=False), sa.Column("error_code", sa.String(64)), sa.Column("error_message", sa.Text()), sa.Column("version_id", sa.String(36)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.ForeignKeyConstraint(["project_id"], ["business_case_projects.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["version_id"], ["business_case_versions.id"], ondelete="SET NULL"))
    op.create_index("ix_generation_runs_project_created", "generation_runs", ["project_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_generation_runs_project_created", table_name="generation_runs")
    op.drop_table("generation_runs")
    op.drop_table("assumptions")
    op.drop_table("citation_snapshots")
    op.drop_table("quality_reports")
    op.drop_table("financial_scenarios")
    op.drop_table("business_case_versions")
    op.drop_index("ix_rule_versions_definition_status", table_name="rule_versions")
    op.drop_table("rule_versions")
    op.drop_table("rule_definitions")
