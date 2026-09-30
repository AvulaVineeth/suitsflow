import subprocess
import sys
from io import BytesIO
from unittest.mock import patch

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from suitsflow.services.extraction import ExtractionTooLarge, InvalidTextContent
from suitsflow.services.pdf_text import PdfExtractionUnavailable, extract_pdf_text


def pdf(text="Contract terms", pages=1, encrypted=False):
    writer = PdfWriter()
    for _ in range(pages):
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = stream
    if encrypted:
        writer.encrypt("test-password")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.mark.skipif(sys.platform != "linux", reason="Resource-limited worker runs on Linux")
def test_real_pdf_worker():
    assert "Contract terms" in extract_pdf_text(pdf())
    with pytest.raises(InvalidTextContent):
        extract_pdf_text(pdf(encrypted=True))
    with pytest.raises(InvalidTextContent):
        extract_pdf_text(pdf(text=""))
    with pytest.raises(InvalidTextContent):
        extract_pdf_text(b"%PDF-1.4\n")
    with pytest.raises(ExtractionTooLarge):
        extract_pdf_text(pdf(pages=101))


@pytest.mark.parametrize(
    "code,error",
    [
        (3, ExtractionTooLarge),
        (-9, ExtractionTooLarge),
        (4, InvalidTextContent),
        (5, PdfExtractionUnavailable),
    ],
)
def test_child_failures_never_return_partial_text(code, error):
    with (
        patch("suitsflow.services.pdf_text.platform.system", return_value="Linux"),
        patch(
            "suitsflow.services.pdf_text.subprocess.run",
            return_value=subprocess.CompletedProcess([], code, b"partial text"),
        ),
        pytest.raises(error),
    ):
        extract_pdf_text(b"pdf")


def test_timeout_and_capacity_are_bounded():
    with (
        patch("suitsflow.services.pdf_text.platform.system", return_value="Linux"),
        patch(
            "suitsflow.services.pdf_text.subprocess.run",
            side_effect=subprocess.TimeoutExpired("worker", 15),
        ),
        pytest.raises(ExtractionTooLarge),
    ):
        extract_pdf_text(b"pdf")
    with (
        patch("suitsflow.services.pdf_text.platform.system", return_value="Linux"),
        patch("suitsflow.services.pdf_text._slots") as slots,
    ):
        slots.acquire.return_value = False
        with pytest.raises(PdfExtractionUnavailable):
            extract_pdf_text(b"pdf")
        slots.release.assert_not_called()


def test_unsupported_host_never_starts_child():
    with (
        patch("suitsflow.services.pdf_text.platform.system", return_value="Windows"),
        patch("suitsflow.services.pdf_text.subprocess.run") as run,
    ):
        with pytest.raises(PdfExtractionUnavailable):
            extract_pdf_text(b"pdf")
        run.assert_not_called()
