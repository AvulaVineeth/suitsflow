from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from suitsflow.services.docx_text import MAX_XML_BYTES, extract_docx_body
from suitsflow.services.extraction import ExtractionTooLarge, InvalidTextContent

NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def docx(xml: bytes, extra=None) -> bytes:
    target = BytesIO()
    with ZipFile(target, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", xml)
        for name, value in (extra or {}).items():
            archive.writestr(name, value)
    return target.getvalue()


def document(body: str) -> bytes:
    return f'<w:document xmlns:w="{NS}"><w:body>{body}</w:body></w:document>'.encode()


def test_docx_body_paragraphs_tables_and_unicode():
    content = docx(
        document(
            "<w:p><w:r><w:t>Terms café</w:t><w:tab/>"
            "<w:t>one</w:t><w:br/><w:t>two</w:t></w:r></w:p>"
            "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Cell</w:t>"
            "</w:r></w:p></w:tc></w:tr></w:tbl>"
        ),
        {"word/header1.xml": "<ignored>Header</ignored>"},
    )
    assert extract_docx_body(content) == "Terms café\tone\ntwo\nCell\n"


@pytest.mark.parametrize(
    "xml",
    [
        b"<broken>",
        b"<root/>",
        f'<w:document xmlns:w="{NS}"/>'.encode(),
        b'<!DOCTYPE x [<!ENTITY e SYSTEM "file:///never-read">]><x>&e;</x>',
        document("<w:ins><w:r><w:t>change</w:t></w:r></w:ins>"),
        document("<w:altChunk/>"),
    ],
)
def test_invalid_or_unsupported_xml_is_rejected(xml):
    with pytest.raises(InvalidTextContent):
        extract_docx_body(docx(xml))


def test_external_relationship_is_not_followed():
    content = docx(
        document("<w:p><w:r><w:t>Link label</w:t></w:r></w:p>"),
        {
            "word/_rels/document.xml.rels": "<Relationships>"
            '<Relationship Target="http://127.0.0.1:1/" '
            'TargetMode="External"/></Relationships>'
        },
    )
    assert extract_docx_body(content) == "Link label\n"


@pytest.mark.parametrize(
    "xml",
    [
        document("<w:p><w:r><w:t>" + "a" * 1_000_001 + "</w:t></w:r></w:p>"),
        document("<w:x>" * 65 + "</w:x>" * 65),
        b"x" * (MAX_XML_BYTES + 1),
        document("<w:r/>" * 100_001),
    ],
    ids=["characters", "depth", "xml-size", "node-count"],
)
def test_parser_resource_limits(xml):
    with pytest.raises(ExtractionTooLarge):
        extract_docx_body(docx(xml))


def test_invalid_zip_and_missing_document():
    with pytest.raises(InvalidTextContent):
        extract_docx_body(b"not a zip")
    target = BytesIO()
    with ZipFile(target, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
    with pytest.raises(InvalidTextContent):
        extract_docx_body(target.getvalue())


def test_duplicate_archive_names_are_rejected():
    with pytest.warns(UserWarning, match="Duplicate name"):
        content = docx(document(""), {"word/document.xml": document("")})
    with pytest.raises(InvalidTextContent):
        extract_docx_body(content)


def test_archive_limits_are_enforced_before_parsing():
    for content in (
        b"x" * (2 * 1024 * 1024 + 1),
        docx(document(""), {f"unused/{i}": "" for i in range(2000)}),
        docx(document(""), {"unused.bin": b"x" * (16 * 1024 * 1024)}),
    ):
        with pytest.raises(ExtractionTooLarge):
            extract_docx_body(content)
