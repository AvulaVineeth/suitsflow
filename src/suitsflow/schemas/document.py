from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

DocumentType = Literal["contract", "policy", "other"]
MimeType = Literal[
    "application/pdf",
    "text/plain",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]


class DocumentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    document_type: DocumentType


class VersionCreate(BaseModel):
    """Declared file metadata only; no uploaded bytes have been verified."""

    model_config = ConfigDict(extra="forbid")
    mime_type: MimeType
    file_size: Annotated[int, Field(strict=True, gt=0, le=104857600)]
    checksum: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    document_type: DocumentType
    status: Literal["draft"]
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class VersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    document_id: UUID
    version_number: int
    mime_type: MimeType
    file_size: int
    checksum: str
    uploaded_at: datetime | None
    created_by: UUID
    created_at: datetime
