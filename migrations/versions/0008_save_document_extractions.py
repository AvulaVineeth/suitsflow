"""Save immutable extracted text with revision and parser provenance.

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_document_versions_source", "document_versions", ["tenant_id", "id", "checksum"]
    )
    op.create_table(
        "document_extractions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("source_checksum", sa.String(64), nullable=False),
        sa.Column("extractor", sa.String(32), nullable=False),
        sa.Column("storage_bucket", sa.String(63), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("storage_version_id", sa.String(1024), nullable=True),
        sa.Column("text_bytes", sa.Integer(), nullable=False),
        sa.Column("character_count", sa.Integer(), nullable=False),
        sa.Column("text_checksum", sa.String(64), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_extractions")),
        sa.UniqueConstraint("tenant_id", "version_id", "extractor", name="uq_extraction_parser"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "version_id", "source_checksum"],
            ["document_versions.tenant_id", "document_versions.id", "document_versions.checksum"],
            name=op.f("fk_document_extractions_tenant_id_document_versions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "created_by"],
            ["users.tenant_id", "users.id"],
            name=op.f("fk_document_extractions_tenant_id_users"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "extractor IN ('plain-text-v1', 'docx-body-v1', 'pdf-text-v1')",
            name=op.f("ck_document_extractions_valid_extractor"),
        ),
        sa.CheckConstraint(
            "character_count >= 0 AND character_count <= 1000000",
            name=op.f("ck_document_extractions_valid_text_length"),
        ),
        sa.CheckConstraint(
            "text_bytes >= 0 AND text_bytes <= 4000000",
            name=op.f("ck_document_extractions_valid_text_bytes"),
        ),
        sa.CheckConstraint(
            "length(storage_bucket) > 0 AND length(storage_key) > 0",
            name=op.f("ck_document_extractions_storage_reference"),
        ),
        sa.CheckConstraint(
            "text_checksum ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_document_extractions_valid_text_checksum"),
        ),
    )
    op.execute("""
        CREATE FUNCTION prevent_extraction_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Saved extraction records are immutable';
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER immutable_extractions
        BEFORE UPDATE OR DELETE OR TRUNCATE ON document_extractions
        FOR EACH STATEMENT EXECUTE FUNCTION prevent_extraction_mutation();
    """)


def downgrade() -> None:
    op.drop_table("document_extractions")
    op.execute("DROP FUNCTION prevent_extraction_mutation()")
    op.drop_constraint("uq_document_versions_source", "document_versions", type_="unique")
