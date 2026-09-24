"""Track scan state and quarantine existing uploaded revisions.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_versions",
        sa.Column("content_status", sa.String(32), nullable=False, server_default="pending_upload"),
    )
    op.add_column("document_versions", sa.Column("scanned_at", sa.DateTime(timezone=True)))
    op.execute(
        "UPDATE document_versions SET content_status = 'pending_scan' WHERE uploaded_at IS NOT NULL"
    )
    op.create_check_constraint(
        "valid_content_status",
        "document_versions",
        "(content_status = 'pending_upload' AND uploaded_at IS NULL AND scanned_at IS NULL) "
        "OR (content_status = 'pending_scan' AND uploaded_at IS NOT NULL AND scanned_at IS NULL) "
        "OR (content_status IN ('clean', 'rejected', 'scan_failed') "
        "AND uploaded_at IS NOT NULL AND scanned_at IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_document_versions_valid_content_status"), "document_versions", type_="check"
    )
    op.drop_column("document_versions", "scanned_at")
    op.drop_column("document_versions", "content_status")
