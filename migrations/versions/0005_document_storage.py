"""Link document revisions to verified stored objects.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("document_versions", sa.Column("storage_bucket", sa.String(63), nullable=True))
    op.add_column("document_versions", sa.Column("storage_key", sa.String(512), nullable=True))
    op.add_column(
        "document_versions", sa.Column("storage_version_id", sa.String(1024), nullable=True)
    )
    op.add_column(
        "document_versions", sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_check_constraint(
        "complete_storage_reference",
        "document_versions",
        "(storage_bucket IS NULL AND storage_key IS NULL AND storage_version_id IS NULL "
        "AND uploaded_at IS NULL) OR (storage_bucket IS NOT NULL AND "
        "length(storage_bucket) > 0 AND storage_key IS NOT NULL AND "
        "length(storage_key) > 0 AND uploaded_at IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_document_versions_complete_storage_reference"), "document_versions", type_="check"
    )
    for name in ("uploaded_at", "storage_version_id", "storage_key", "storage_bucket"):
        op.drop_column("document_versions", name)
