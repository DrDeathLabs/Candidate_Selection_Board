"""Add missing performance indexes on heavily-queried foreign key columns."""

from __future__ import annotations

from alembic import op

revision = "0005_performance_indexes"
down_revision = "0004_board_meeting_transcript"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_candidate_matches_case_candidate", "candidate_matches", ["case_id", "candidate_id"])
    op.create_index("ix_candidate_facts_candidate_id", "candidate_facts", ["candidate_id"])
    op.create_index("ix_expert_reviews_candidate_id", "expert_reviews", ["candidate_id"])
    op.create_index("ix_challenge_findings_candidate_id", "challenge_findings", ["candidate_id"])
    op.create_index("ix_audit_events_case_id", "audit_events", ["case_id"])
    op.create_index("ix_evidence_items_case_id", "evidence_items", ["case_id"])


def downgrade() -> None:
    op.drop_index("ix_candidate_matches_case_candidate", table_name="candidate_matches")
    op.drop_index("ix_candidate_facts_candidate_id", table_name="candidate_facts")
    op.drop_index("ix_expert_reviews_candidate_id", table_name="expert_reviews")
    op.drop_index("ix_challenge_findings_candidate_id", table_name="challenge_findings")
    op.drop_index("ix_audit_events_case_id", table_name="audit_events")
    op.drop_index("ix_evidence_items_case_id", table_name="evidence_items")
