"""Add session_id and source_ip to audit_events for FISMA AU-2 compliance."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_audit_session_fields"
down_revision = "0006_auth_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audit_events", sa.Column("session_id", sa.String(36), nullable=True))
    op.add_column("audit_events", sa.Column("source_ip", sa.String(45), nullable=True))
    op.create_index("ix_audit_events_session_id", "audit_events", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_session_id", table_name="audit_events")
    op.drop_column("audit_events", "source_ip")
    op.drop_column("audit_events", "session_id")
