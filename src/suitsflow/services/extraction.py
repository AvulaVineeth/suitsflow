from uuid import UUID

from suitsflow.core.security import Principal, ResourceNotFound, require_document_access
from suitsflow.repositories.documents import DocumentRepository
from suitsflow.schemas.extraction import TextExtractionResponse
from suitsflow.services.downloads import ContentNotCleared, DownloadService
from suitsflow.services.storage import ObjectStorage

MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_TEXT_CHARACTERS = 1_000_000


class UnsupportedExtraction(Exception):
    pass


class InvalidTextContent(Exception):
    pass


class ExtractionTooLarge(Exception):
    pass


def extract_plain_text(content: bytes) -> str:
    """Decode without guessing encodings, dropping invalid bytes, or truncating text."""
    if len(content) > MAX_SOURCE_BYTES:
        raise ExtractionTooLarge
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InvalidTextContent from exc
    if len(text) > MAX_TEXT_CHARACTERS:
        raise ExtractionTooLarge
    if any(ord(char) < 32 and char not in "\t\n\r" for char in text) or "\x7f" in text:
        raise InvalidTextContent
    return text


class ExtractionService:
    def __init__(self, repository: DocumentRepository, storage: ObjectStorage) -> None:
        self.repository = repository
        self.storage = storage

    async def extract(
        self, principal: Principal, document_id: UUID, version_id: UUID
    ) -> TextExtractionResponse:
        require_document_access(principal)
        version = await self.repository.version(principal.tenant_id, document_id, version_id)
        if version is None:
            raise ResourceNotFound
        if version.content_status != "clean":
            raise ContentNotCleared
        if version.mime_type != "text/plain":
            raise UnsupportedExtraction
        if version.file_size > MAX_SOURCE_BYTES:
            raise ExtractionTooLarge
        number, checksum = version.version_number, version.checksum
        download = await DownloadService(self.repository, self.storage).download(
            principal, document_id, version_id
        )
        try:
            text = extract_plain_text(download.body.read(MAX_SOURCE_BYTES + 1))
        finally:
            download.body.close()
        return TextExtractionResponse(
            document_id=document_id,
            version_id=version_id,
            version_number=number,
            source_checksum=checksum,
            text=text,
            character_count=len(text),
        )
