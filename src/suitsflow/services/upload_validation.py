"""Bounded integrity and basic format checks, not malware scanning or full parsing."""

import codecs
import zlib
from typing import BinaryIO
from zipfile import BadZipFile, ZipFile


class InvalidUpload(Exception):
    pass


def validate_format(body: BinaryIO, mime_type: str) -> None:
    body.seek(0)
    try:
        if mime_type == "application/pdf":
            if not body.read(8).startswith(b"%PDF-"):
                raise InvalidUpload("File does not have a PDF signature")
        elif mime_type == "text/plain":
            decoder = codecs.getincrementaldecoder("utf-8")("strict")
            while chunk := body.read(65536):
                if b"\x00" in chunk:
                    raise InvalidUpload("Text must be UTF-8 without NUL bytes")
                decoder.decode(chunk)
            decoder.decode(b"", final=True)
        else:
            with ZipFile(body) as archive:
                entries = archive.infolist()
                names = [entry.filename for entry in entries]
                if (
                    len(entries) > 2000
                    or len(names) != len(set(names))
                    or not {"[Content_Types].xml", "word/document.xml"}.issubset(names)
                    or sum(entry.file_size for entry in entries) > 200 * 1024 * 1024
                    or any(entry.flag_bits & 1 for entry in entries)
                ):
                    raise InvalidUpload("File does not have a supported DOCX structure")
                # Stream entries to check CRCs without extracting files or loading XML.
                if archive.testzip() is not None:
                    raise InvalidUpload("DOCX archive is corrupt")
    except (
        UnicodeDecodeError,
        BadZipFile,
        RuntimeError,
        NotImplementedError,
        zlib.error,
        EOFError,
    ) as exc:
        raise InvalidUpload("File does not match its declared format") from exc
    finally:
        body.seek(0)
