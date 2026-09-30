"""Run PDF parsing in a bounded Linux child process, outside the API interpreter."""

import platform
import subprocess
import sys
from threading import BoundedSemaphore

from suitsflow.services.extraction import MAX_SOURCE_BYTES, ExtractionTooLarge, InvalidTextContent

_slots = BoundedSemaphore(2)


class PdfExtractionUnavailable(Exception):
    pass


def extract_pdf_text(content: bytes) -> str:
    if len(content) > MAX_SOURCE_BYTES:
        raise ExtractionTooLarge
    if platform.system() != "Linux" or not _slots.acquire(blocking=False):
        raise PdfExtractionUnavailable
    try:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "suitsflow.pdf_worker"],
                input=content,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=15,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ExtractionTooLarge from exc
        except OSError as exc:
            raise PdfExtractionUnavailable from exc
        if result.returncode == 3 or result.returncode < 0:
            raise ExtractionTooLarge
        if result.returncode == 5:
            raise PdfExtractionUnavailable
        if result.returncode != 0:
            raise InvalidTextContent
        try:
            return result.stdout.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise InvalidTextContent from exc
    finally:
        _slots.release()
