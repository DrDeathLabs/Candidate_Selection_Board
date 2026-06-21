"""Add parsed_profile JSONB column to resume segments."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_resume_seg_parsed_profile"
down_revision = "0002_resume_seg_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "resume_segments",
        sa.Column("parsed_profile", postgresql.JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("resume_segments", "parsed_profile")
