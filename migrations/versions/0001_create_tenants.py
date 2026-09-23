"""Create the tenant root for the initial database foundation."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_tenants_name_not_blank"),
        sa.CheckConstraint("status IN ('active', 'suspended')", name="ck_tenants_valid_status"),
        sa.PrimaryKeyConstraint("id", name="pk_tenants"),
    )


def downgrade() -> None:
    op.drop_table("tenants")
