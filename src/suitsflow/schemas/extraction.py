from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class TextExtractionResponse(BaseModel):
    document_id: UUID
    version_id: UUID
    version_number: int
    source_checksum: str
    extractor: Literal["plain-text-v1", "docx-body-v1", "pdf-text-v1"] = "plain-text-v1"
    text: str
    character_count: int
