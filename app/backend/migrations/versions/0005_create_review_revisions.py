"""Create review comments, proposals and version changes."""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "review_comments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version_id", sa.String(36), nullable=False),
        sa.Column("section_id", sa.String(64)),
        sa.Column("block_id", sa.String(120)),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("author", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["version_id"], ["business_case_versions.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_review_comments_version_status", "review_comments", ["version_id", "status"])
    op.create_table(
        "revision_proposals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("comment_id", sa.String(36), nullable=False),
        sa.Column("base_version_id", sa.String(36), nullable=False),
        sa.Column("base_content_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("patch_json", sa.Text(), nullable=False),
        sa.Column("impact_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("applied_version_id", sa.String(36)),
        sa.ForeignKeyConstraint(["comment_id"], ["review_comments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["base_version_id"], ["business_case_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["applied_version_id"], ["business_case_versions.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_revision_proposals_comment_created", "revision_proposals", ["comment_id", "created_at"])
    op.create_table(
        "version_changes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version_id", sa.String(36), nullable=False, unique=True),
        sa.Column("base_version_id", sa.String(36)),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("author", sa.String(120), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("changed_blocks_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["version_id"], ["business_case_versions.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("version_changes")
    op.drop_index("ix_revision_proposals_comment_created", table_name="revision_proposals")
    op.drop_table("revision_proposals")
    op.drop_index("ix_review_comments_version_status", table_name="review_comments")
    op.drop_table("review_comments")
