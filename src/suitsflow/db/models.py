from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from suitsflow.db.base import Base


class Tenant(Base):
    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint("status IN ('active', 'suspended')", name="valid_status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), server_default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint(
            "length(email) > 0 AND email = lower(trim(email))", name="email_normalized"
        ),
        CheckConstraint("status IN ('active', 'disabled')", name="valid_status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"))
    email: Mapped[str] = mapped_column(String(320))
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), server_default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "name", name="uq_roles_tenant_name"),
        CheckConstraint("name IN ('tenant_admin', 'member')", name="valid_name"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "user_id"], ["users.tenant_id", "users.id"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "role_id"], ["roles.tenant_id", "roles.id"], ondelete="RESTRICT"
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(primary_key=True)
    role_id: Mapped[UUID] = mapped_column(primary_key=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "user_id"], ["users.tenant_id", "users.id"], ondelete="RESTRICT"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), index=True
    )
    user_id: Mapped[UUID] = mapped_column()
    action: Mapped[str] = mapped_column(String(100))
    resource_type: Mapped[str] = mapped_column(String(100))
    resource_id: Mapped[UUID] = mapped_column()
    details: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "created_by"], ["users.tenant_id", "users.id"], ondelete="RESTRICT"
        ),
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint("document_type IN ('contract', 'policy', 'other')", name="valid_type"),
        CheckConstraint("status = 'draft'", name="valid_status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(255))
    document_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), server_default="draft")
    created_by: Mapped[UUID] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "document_id", "version_number", name="uq_document_versions_number"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["documents.tenant_id", "documents.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "created_by"], ["users.tenant_id", "users.id"], ondelete="RESTRICT"
        ),
        CheckConstraint("version_number > 0", name="positive_number"),
        CheckConstraint(
            "(content_status = 'pending_upload' AND uploaded_at IS NULL AND scanned_at IS NULL) "
            "OR (content_status = 'pending_scan' AND uploaded_at IS NOT NULL "
            "AND scanned_at IS NULL) "
            "OR (content_status IN ('clean', 'rejected', 'scan_failed') "
            "AND uploaded_at IS NOT NULL AND scanned_at IS NOT NULL)",
            name="valid_content_status",
        ),
        CheckConstraint(
            "(storage_bucket IS NULL AND storage_key IS NULL AND storage_version_id IS NULL "
            "AND uploaded_at IS NULL) OR (storage_bucket IS NOT NULL AND "
            "length(storage_bucket) > 0 AND storage_key IS NOT NULL AND "
            "length(storage_key) > 0 AND uploaded_at IS NOT NULL)",
            name="complete_storage_reference",
        ),
        CheckConstraint("file_size > 0 AND file_size <= 104857600", name="valid_file_size"),
        CheckConstraint("checksum ~ '^[0-9a-f]{64}$'", name="valid_checksum"),
        CheckConstraint(
            "mime_type IN ('application/pdf', 'text/plain', "
            "'application/vnd.openxmlformats-officedocument.wordprocessingml.document')",
            name="valid_mime_type",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column()
    document_id: Mapped[UUID] = mapped_column()
    version_number: Mapped[int] = mapped_column(Integer)
    mime_type: Mapped[str] = mapped_column(String(100))
    file_size: Mapped[int] = mapped_column(BigInteger)
    checksum: Mapped[str] = mapped_column(String(64))
    storage_bucket: Mapped[str | None] = mapped_column(String(63))
    storage_key: Mapped[str | None] = mapped_column(String(512))
    storage_version_id: Mapped[str | None] = mapped_column(String(1024))
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_status: Mapped[str] = mapped_column(String(32), server_default="pending_upload")
    scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
