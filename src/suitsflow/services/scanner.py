import socket
import struct
import time
from typing import BinaryIO, Literal, Protocol
from zipfile import BadZipFile, ZipFile, is_zipfile

ScanVerdict = Literal["clean", "rejected"]


class ScannerUnavailable(Exception):
    pass


class Scanner(Protocol):
    def scan(self, body: BinaryIO) -> ScanVerdict: ...


class ClamAVScanner:
    """INSTREAM client for a trusted, privately reachable clamd daemon."""

    def __init__(
        self,
        host: str,
        port: int,
        timeout: float,
        *,
        max_file_bytes: int = 104857600,
        max_scan_bytes: int = 314572800,
    ) -> None:
        self.host, self.port, self.timeout = host, port, timeout
        self.max_file_bytes, self.max_scan_bytes = max_file_bytes, max_scan_bytes

    def _within_limits(self, body: BinaryIO) -> bool:
        """Do not rely on daemon alerts for oversized ZIP members: some are skipped."""
        body.seek(0, 2)
        size = body.tell()
        if size > self.max_file_bytes:
            return False
        body.seek(0)
        if is_zipfile(body):
            with ZipFile(body) as archive:
                entries = archive.infolist()
                if (
                    len(entries) > 2000
                    or any(entry.file_size > self.max_file_bytes for entry in entries)
                    or size + sum(entry.file_size for entry in entries) > self.max_scan_bytes
                ):
                    return False
        return True

    def scan(self, body: BinaryIO) -> ScanVerdict:
        deadline = time.monotonic() + self.timeout

        def remaining() -> float:
            duration = deadline - time.monotonic()
            if duration <= 0:
                raise ScannerUnavailable
            return duration

        body.seek(0)
        try:
            if not self._within_limits(body):
                return "rejected"
            body.seek(0)
            with socket.create_connection(
                (self.host, self.port), timeout=remaining()
            ) as connection:
                connection.settimeout(remaining())
                connection.sendall(b"zINSTREAM\x00")
                while chunk := body.read(65536):
                    connection.settimeout(remaining())
                    connection.sendall(struct.pack("!I", len(chunk)) + chunk)
                connection.settimeout(remaining())
                connection.sendall(struct.pack("!I", 0))
                response = bytearray()
                while b"\x00" not in response:
                    connection.settimeout(remaining())
                    chunk = connection.recv(1024)
                    if not chunk or len(response) + len(chunk) > 4096:
                        raise ScannerUnavailable
                    response.extend(chunk)
                result, _, trailing = bytes(response).partition(b"\x00")
                if trailing:
                    raise ScannerUnavailable
                if result == b"stream: OK":
                    return "clean"
                if result.startswith(b"stream: ") and result.endswith(b" FOUND"):
                    return "rejected"
                raise ScannerUnavailable
        except (OSError, BadZipFile) as exc:
            raise ScannerUnavailable from exc
        finally:
            body.seek(0)
