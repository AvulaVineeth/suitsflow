from io import BytesIO
from zipfile import ZipFile

import pytest

from suitsflow.services.upload_validation import InvalidUpload, validate_format

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.mark.parametrize(
    ("content", "mime_type"),
    [(b"%PDF-1.7\n", "application/pdf"), ("Agreement: £100".encode(), "text/plain")],
)
def test_supported_signatures(content: bytes, mime_type: str) -> None:
    body = BytesIO(content)
    validate_format(body, mime_type)
    assert body.tell() == 0


@pytest.mark.parametrize(
    ("content", "mime_type"),
    [
        (b"plain", "application/pdf"),
        (b"\xff", "text/plain"),
        (b"a\x00b", "text/plain"),
        (b"PK not a zip", DOCX),
    ],
)
def test_invalid_format(content: bytes, mime_type: str) -> None:
    with pytest.raises(InvalidUpload):
        validate_format(BytesIO(content), mime_type)


def test_docx_structure_and_corruption() -> None:
    body = BytesIO()
    with ZipFile(body, "w") as archive:
        archive.writestr("word/document.xml", "<document/>")
    with pytest.raises(InvalidUpload):
        validate_format(body, DOCX)
    with ZipFile(body, "a") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
    validate_format(body, DOCX)
    corrupt = body.getvalue().replace(b"<document/>", b"!document/>")
    with pytest.raises(InvalidUpload):
        validate_format(BytesIO(corrupt), DOCX)
