from io import BytesIO
from unittest.mock import MagicMock, patch
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from suitsflow.services.scanner import ClamAVScanner, ScannerUnavailable


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ([b"stream: O", b"K\x00"], "clean"),
        ([b"stream: Eicar-Signature FOUND\x00"], "rejected"),
    ],
)
def test_clamd_stream_protocol(response, expected) -> None:
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.recv.side_effect = response
    body = BytesIO(b"example")
    with patch("socket.create_connection", return_value=connection):
        assert ClamAVScanner("localhost", 3310, 2).scan(body) == expected
    assert b"".join(call.args[0] for call in connection.sendall.call_args_list) == (
        b"zINSTREAM\x00\x00\x00\x00\x07example\x00\x00\x00\x00"
    )
    connection.__exit__.assert_called_once()
    assert body.tell() == 0


@pytest.mark.parametrize(
    "response",
    [
        [b"stream: too large ERROR\x00"],
        [b""],
        [b"stream: OK", b""],
        [b"stream: OK\x00garbage"],
        [b"x" * 4097],
        [b"unknown\x00"],
    ],
)
def test_clamd_errors_fail_closed(response) -> None:
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.recv.side_effect = response
    with (
        patch("socket.create_connection", return_value=connection),
        pytest.raises(ScannerUnavailable),
    ):
        ClamAVScanner("localhost", 3310, 2).scan(BytesIO(b"example"))
    connection.__exit__.assert_called_once()


def test_clamd_network_failure() -> None:
    with (
        patch("socket.create_connection", side_effect=TimeoutError),
        pytest.raises(ScannerUnavailable),
    ):
        ClamAVScanner("localhost", 3310, 2).scan(BytesIO(b"example"))


@pytest.mark.parametrize("kind", ["file", "member", "total"])
def test_size_policy_rejects_before_contacting_daemon(kind: str) -> None:
    body = BytesIO(b"x" * 1201)
    if kind != "file":
        body = BytesIO()
        with ZipFile(body, "w", ZIP_DEFLATED) as archive:
            if kind == "member":
                archive.writestr("large.txt", b"x" * 1201)
            else:
                for index in range(3):
                    archive.writestr(f"{index}.txt", b"x" * 400)
    scanner = ClamAVScanner("localhost", 3310, 2, max_file_bytes=1200, max_scan_bytes=1300)
    with patch("socket.create_connection") as connect:
        assert scanner.scan(body) == "rejected"
    connect.assert_not_called()
    assert body.tell() == 0
