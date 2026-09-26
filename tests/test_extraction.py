import asyncio
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from suitsflow.core.security import Principal, ResourceNotFound
from suitsflow.services.downloads import ContentNotCleared, Download
from suitsflow.services.extraction import (
    MAX_SOURCE_BYTES,
    MAX_TEXT_CHARACTERS,
    ExtractionService,
    ExtractionTooLarge,
    InvalidTextContent,
    UnsupportedExtraction,
    extract_plain_text,
)


@pytest.mark.parametrize(
    "content,expected",
    [
        (b"", ""),
        (b"\xef\xbb\xbfContract\r\n\tTerms", "Contract\r\n\tTerms"),
        ("Legal café — 合同".encode(), "Legal café — 合同"),
        (b"<script>alert(1)</script>", "<script>alert(1)</script>"),
    ],
)
def test_lossless_utf8_text(content, expected):
    assert extract_plain_text(content) == expected


@pytest.mark.parametrize("content", [b"\xff", b"hello\x00world", b"\x1b[0m", b"\x7f"])
def test_rejects_invalid_utf8_and_controls(content):
    with pytest.raises(InvalidTextContent):
        extract_plain_text(content)


def test_limits_reject_instead_of_truncating():
    assert len(extract_plain_text(b"a" * MAX_TEXT_CHARACTERS)) == MAX_TEXT_CHARACTERS
    for content in (b"a" * (MAX_TEXT_CHARACTERS + 1), b"a" * (MAX_SOURCE_BYTES + 1)):
        with pytest.raises(ExtractionTooLarge):
            extract_plain_text(content)


@pytest.mark.parametrize("failure", [None, "encoding", "too_large"])
def test_extraction_closes_file_and_preserves_provenance(failure):
    content = {None: b"Terms", "encoding": b"\xff", "too_large": b"a" * (MAX_SOURCE_BYTES + 1)}[
        failure
    ]
    body = BytesIO(content)
    document_id, version_id = uuid4(), uuid4()
    principal = Principal(uuid4(), uuid4(), frozenset({"member"}))
    version = SimpleNamespace(
        content_status="clean",
        mime_type="text/plain",
        file_size=5,
        version_number=7,
        checksum="a" * 64,
    )
    repo = SimpleNamespace(version=AsyncMock(return_value=version))
    with patch(
        "suitsflow.services.extraction.DownloadService.download",
        new=AsyncMock(return_value=Download(body, len(content), "revision.txt")),
    ):
        if failure:
            with pytest.raises(InvalidTextContent if failure == "encoding" else ExtractionTooLarge):
                asyncio.run(
                    ExtractionService(repo, Mock()).extract(principal, document_id, version_id)
                )
        else:
            result = asyncio.run(
                ExtractionService(repo, Mock()).extract(principal, document_id, version_id)
            )
            assert result.document_id == document_id
            assert result.version_id == version_id
            assert result.version_number == 7
            assert result.source_checksum == "a" * 64
            assert result.extractor == "plain-text-v1"
            assert result.text == "Terms"
            assert result.character_count == 5
    assert body.closed


@pytest.mark.parametrize(
    "change,error",
    [
        ({"content_status": "pending_scan"}, ContentNotCleared),
        ({"mime_type": "application/pdf"}, UnsupportedExtraction),
        ({"file_size": MAX_SOURCE_BYTES + 1}, ExtractionTooLarge),
        (None, ResourceNotFound),
    ],
)
def test_rejects_before_reading_storage(change, error):
    values = dict(content_status="clean", mime_type="text/plain", file_size=5)
    version = SimpleNamespace(**(values | change)) if change else None
    repo = SimpleNamespace(version=AsyncMock(return_value=version))
    storage = Mock()
    with pytest.raises(error):
        asyncio.run(
            ExtractionService(repo, storage).extract(
                Principal(uuid4(), uuid4(), frozenset({"member"})), uuid4(), uuid4()
            )
        )
    storage.download.assert_not_called()
