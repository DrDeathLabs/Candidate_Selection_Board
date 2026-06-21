"""Add inferred identity fields to resume segments."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_resume_seg_identity"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("resume_segments", sa.Column("inferred_name", sa.String(length=255), nullable=True))
    op.add_column("resume_segments", sa.Column("inferred_email", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("resume_segments", "inferred_email")
    op.drop_column("resume_segments", "inferred_name")
