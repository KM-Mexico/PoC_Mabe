"""Create source documents and evidence chunks."""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_documents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("original_name", sa.String(length=180), nullable=False),
        sa.Column("storage_name", sa.String(length=36), nullable=False),
        sa.Column("media_type", sa.String(length=100), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("included", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("byte_size >= 0", name="ck_documents_byte_size"),
        sa.ForeignKeyConstraint(["project_id"], ["business_case_projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("storage_name", name="uq_documents_storage_name"),
        sa.UniqueConstraint("project_id", "sha256", name="uq_documents_project_sha256"),
    )
    op.create_index("ix_documents_project_updated", "source_documents", ["project_id", "updated_at"])
    op.create_table(
        "evidence_chunks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("sheet_name", sa.String(length=120), nullable=True),
        sa.Column("cell_range", sa.String(length=40), nullable=True),
        sa.Column("included", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.CheckConstraint("ordinal >= 0", name="ck_chunks_ordinal"),
        sa.ForeignKeyConstraint(["document_id"], ["source_documents.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("document_id", "ordinal", name="uq_chunks_document_ordinal"),
    )
    op.create_index("ix_chunks_document_included", "evidence_chunks", ["document_id", "included"])


def downgrade() -> None:
    op.drop_index("ix_chunks_document_included", table_name="evidence_chunks")
    op.drop_table("evidence_chunks")
    op.drop_index("ix_documents_project_updated", table_name="source_documents")
    op.drop_table("source_documents")
