"""Bounded main-body text extraction; no relationship resolution or file extraction."""

import zlib
from io import BytesIO
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile, ZipFile

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import iterparse

from suitsflow.services.extraction import (
    MAX_SOURCE_BYTES,
    MAX_TEXT_CHARACTERS,
    ExtractionTooLarge,
    InvalidTextContent,
)

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MAX_XML_BYTES = 4 * 1024 * 1024


def extract_docx_body(content: bytes) -> str:
    if len(content) > MAX_SOURCE_BYTES:
        raise ExtractionTooLarge
    try:
        with ZipFile(BytesIO(content)) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if len(entries) > 2000 or sum(e.file_size for e in entries) > 16 * 1024 * 1024:
                raise ExtractionTooLarge
            if (
                len(names) != len(set(names))
                or any(e.flag_bits & 1 for e in entries)
                or not {"[Content_Types].xml", "word/document.xml"}.issubset(names)
            ):
                raise InvalidTextContent
            if archive.getinfo("word/document.xml").file_size > MAX_XML_BYTES:
                raise ExtractionTooLarge
            with archive.open("word/document.xml") as source:
                xml = source.read(MAX_XML_BYTES + 1)
            if len(xml) > MAX_XML_BYTES:
                raise ExtractionTooLarge
        parts: list[str] = []
        length = depth = nodes = body_depth = bodies = 0
        for event, element in iterparse(BytesIO(xml), events=("start", "end"), forbid_dtd=True):
            if event == "start":
                depth += 1
                nodes += 1
                if depth > 64 or nodes > 100_000:
                    raise ExtractionTooLarge
                if depth == 1 and element.tag != W + "document":
                    raise InvalidTextContent
                if element.tag == W + "body":
                    if depth != 2 or bodies:
                        raise InvalidTextContent
                    bodies += 1
                    body_depth = depth
                # These need an explicit revision/content policy before extraction.
                if element.tag in {
                    W + "ins",
                    W + "del",
                    W + "moveFrom",
                    W + "moveTo",
                    W + "altChunk",
                }:
                    raise InvalidTextContent
                continue
            piece = ""
            if body_depth:
                if element.tag == W + "t":
                    piece = element.text or ""
                elif element.tag == W + "tab":
                    piece = "\t"
                elif element.tag in {W + "br", W + "cr", W + "p"}:
                    piece = "\n"
                if depth == body_depth:
                    body_depth = 0
            length += len(piece)
            if length > MAX_TEXT_CHARACTERS:
                raise ExtractionTooLarge
            if piece:
                parts.append(piece)
            element.clear()
            depth -= 1
        if bodies != 1:
            raise InvalidTextContent
        return "".join(parts)
    except (
        BadZipFile,
        KeyError,
        RuntimeError,
        NotImplementedError,
        zlib.error,
        EOFError,
        ParseError,
        DefusedXmlException,
    ) as exc:
        raise InvalidTextContent from exc
