"""Add board_meeting_transcripts table for council deliberation."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_board_meeting_transcript"
down_revision = "0003_resume_seg_parsed_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "board_meeting_transcripts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), onupdate=sa.text("now()"), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("review_cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_name", sa.String(256), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="in_progress"),
        sa.Column("agent_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("round_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("phase1_turns", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("phase2_turns", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("phase3_synthesis", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("full_transcript", sa.Text(), nullable=True),
        sa.Column("meeting_notes", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("meeting_summary", sa.Text(), nullable=True),
    )
    op.create_index("ix_bmt_case_id", "board_meeting_transcripts", ["case_id"])
    op.create_index("ix_bmt_candidate_id", "board_meeting_transcripts", ["candidate_id"])


def downgrade() -> None:
    op.drop_index("ix_bmt_candidate_id", table_name="board_meeting_transcripts")
    op.drop_index("ix_bmt_case_id", table_name="board_meeting_transcripts")
    op.drop_table("board_meeting_transcripts")
