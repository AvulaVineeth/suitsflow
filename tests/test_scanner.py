from io import BytesIO
from unittest.mock import MagicMock, patch

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
