"""Persist tenant users and roles with same-tenant assignment constraints."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_users_tenant_id"),
        sa.UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_users_tenant_id_tenants", ondelete="RESTRICT"
        ),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_users_name_not_blank"),
        sa.CheckConstraint(
            "length(email) > 0 AND email = lower(trim(email))", name="ck_users_email_normalized"
        ),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="ck_users_valid_status"),
    )
    op.create_table(
        "roles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_roles"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_roles_tenant_id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_roles_tenant_name"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_roles_tenant_id_tenants", ondelete="RESTRICT"
        ),
        sa.CheckConstraint("name IN ('tenant_admin', 'member')", name="ck_roles_valid_name"),
    )
    op.create_table(
        "user_roles",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "user_id", "role_id", name="pk_user_roles"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_user_roles_tenant_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "role_id"],
            ["roles.tenant_id", "roles.id"],
            name="fk_user_roles_tenant_id_roles",
            ondelete="RESTRICT",
        ),
    )


def downgrade() -> None:
    op.drop_table("user_roles")
    op.drop_table("roles")
    op.drop_table("users")
