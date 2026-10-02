from typing import Literal
from uuid import UUID

from starlette.concurrency import run_in_threadpool

from suitsflow.core.security import Principal, ResourceNotFound, require_document_access
from suitsflow.repositories.documents import DocumentRepository
from suitsflow.schemas.extraction import TextExtractionResponse
from suitsflow.services.downloads import ContentNotCleared, DownloadService
from suitsflow.services.storage import ObjectStorage

MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_TEXT_CHARACTERS = 1_000_000

ExtractorName = Literal["plain-text-v1", "docx-body-v1", "pdf-text-v1"]


def extractor_for(mime: str) -> ExtractorName:
    if mime == "text/plain":
        return "plain-text-v1"
    if mime == "application/pdf":
        return "pdf-text-v1"
    if mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return "docx-body-v1"
    raise UnsupportedExtraction


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
        from suitsflow.services.docx_text import DOCX_MIME, extract_docx_body
        from suitsflow.services.pdf_text import extract_pdf_text

        if version.mime_type not in {"text/plain", DOCX_MIME, "application/pdf"}:
            raise UnsupportedExtraction
        if version.file_size > MAX_SOURCE_BYTES:
            raise ExtractionTooLarge
        number, checksum, mime = version.version_number, version.checksum, version.mime_type
        download = await DownloadService(self.repository, self.storage).download(
            principal, document_id, version_id
        )
        try:
            content = download.body.read(MAX_SOURCE_BYTES + 1)
            parser = {
                "text/plain": extract_plain_text,
                DOCX_MIME: extract_docx_body,
                "application/pdf": extract_pdf_text,
            }[mime]
            text = await run_in_threadpool(parser, content)
        finally:
            download.body.close()
        return TextExtractionResponse(
            document_id=document_id,
            version_id=version_id,
            version_number=number,
            source_checksum=checksum,
            extractor=extractor_for(mime),
            text=text,
            character_count=len(text),
        )
