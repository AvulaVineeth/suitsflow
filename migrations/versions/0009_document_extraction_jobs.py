"""create_document_extraction_jobs

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_extraction_result",
        "document_extractions",
        ["tenant_id", "version_id", "extractor", "id"],
    )
    op.create_table(
        "document_extraction_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("extractor", sa.String(32), nullable=False),
        sa.Column("result_id", sa.Uuid(), nullable=True),
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
            name=op.f("ck_document_extraction_jobs_valid_claim"),
        ),
        sa.CheckConstraint(
            "attempts >= 0", name=op.f("ck_document_extraction_jobs_valid_attempts")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "requested_by"],
            ["users.tenant_id", "users.id"],
            name=op.f("fk_document_extraction_jobs_tenant_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "version_id"],
            ["document_versions.tenant_id", "document_versions.id"],
            name=op.f("fk_document_extraction_jobs_tenant_id_document_versions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "version_id", "extractor", "result_id"],
            [
                "document_extractions.tenant_id",
                "document_extractions.version_id",
                "document_extractions.extractor",
                "document_extractions.id",
            ],
            name=op.f("fk_document_extraction_jobs_tenant_id_document_extractions"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "(status = 'completed' AND result_id IS NOT NULL) OR "
            "(status <> 'completed' AND result_id IS NULL)",
            name=op.f("ck_document_extraction_jobs_valid_result"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_extraction_jobs")),
        sa.UniqueConstraint(
            "tenant_id",
            "version_id",
            "extractor",
            name=op.f("uq_document_extraction_jobs_tenant_id"),
        ),
    )
    op.create_index(
        op.f("ix_document_extraction_jobs_status"),
        "document_extraction_jobs",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_document_extraction_jobs_status"), table_name="document_extraction_jobs")
    op.drop_table("document_extraction_jobs")
    op.drop_constraint("uq_extraction_result", "document_extractions", type_="unique")
