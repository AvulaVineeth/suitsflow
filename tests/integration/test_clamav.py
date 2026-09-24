"""Opt-in tests against the dedicated local ClamAV test daemon, never a production scanner."""

import os
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from suitsflow.services.scanner import ClamAVScanner, ScannerUnavailable

pytestmark = pytest.mark.scanner
MARKER = b"SuitsFlow harmless scanner integration marker"


@pytest.fixture
def scanner() -> ClamAVScanner:
    port = os.environ.get("SUITSFLOW_TEST_CLAMAV_PORT")
    if not port:
        pytest.skip("Set SUITSFLOW_TEST_CLAMAV_PORT for the dedicated local test scanner")
    return ClamAVScanner(
        "127.0.0.1", int(port), 10, max_file_bytes=1024 * 1024, max_scan_bytes=2 * 1024 * 1024
    )


def test_real_scanner_accepts_ordinary_text(scanner: ClamAVScanner) -> None:
    assert scanner.scan(BytesIO(b"An ordinary agreement with no test marker.")) == "clean"


def test_real_scanner_detects_custom_marker(scanner: ClamAVScanner) -> None:
    assert scanner.scan(BytesIO(MARKER)) == "rejected"


def test_real_scanner_inspects_archive_contents(scanner: ClamAVScanner) -> None:
    archive = BytesIO()
    with ZipFile(archive, "w", ZIP_DEFLATED) as output:
        output.writestr("marker.txt", MARKER)
    assert scanner.scan(archive) == "rejected"


def test_real_scanner_stream_limit_fails_closed(scanner: ClamAVScanner) -> None:
    # Deliberately allow more than the daemon to exercise its wire-level limit error.
    scanner.max_file_bytes = 2 * 1024 * 1024
    with pytest.raises(ScannerUnavailable):
        scanner.scan(BytesIO(b"x" * (1024 * 1024 + 1)))
    # A failed request must not poison the next connection.
    assert scanner.scan(BytesIO(b"ordinary text")) == "clean"


def test_scan_policy_rejects_archive_exceeding_scan_limits(scanner: ClamAVScanner) -> None:
    archive = BytesIO()
    with ZipFile(archive, "w", ZIP_DEFLATED) as output:
        output.writestr("large.txt", b"x" * (2 * 1024 * 1024))
    assert scanner.scan(archive) == "rejected"
