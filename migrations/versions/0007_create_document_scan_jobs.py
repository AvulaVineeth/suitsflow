"""create_document_scan_jobs

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        op.f("uq_document_versions_tenant_id"), "document_versions", ["tenant_id", "id"]
    )
    op.create_table(
        "document_scan_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("claim_token", sa.Uuid(), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(status = 'running' AND claim_token IS NOT NULL AND lease_until IS NOT NULL) OR "
            "(status IN ('pending', 'completed', 'failed') "
            "AND claim_token IS NULL AND lease_until IS NULL)",
            name=op.f("ck_document_scan_jobs_valid_claim"),
        ),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_document_scan_jobs_valid_attempts")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "requested_by"],
            ["users.tenant_id", "users.id"],
            name=op.f("fk_document_scan_jobs_tenant_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "version_id"],
            ["document_versions.tenant_id", "document_versions.id"],
            name=op.f("fk_document_scan_jobs_tenant_id_document_versions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_scan_jobs")),
        sa.UniqueConstraint(
            "tenant_id", "version_id", name=op.f("uq_document_scan_jobs_tenant_id")
        ),
    )
    op.create_index(
        op.f("ix_document_scan_jobs_status"), "document_scan_jobs", ["status"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_document_scan_jobs_status"), table_name="document_scan_jobs")
    op.drop_table("document_scan_jobs")
    op.drop_constraint(op.f("uq_document_versions_tenant_id"), "document_versions", type_="unique")
