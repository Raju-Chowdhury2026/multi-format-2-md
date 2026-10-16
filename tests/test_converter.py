from io import BytesIO
from pathlib import Path
import zipfile

import pytest

from app.converter import ConversionError, baseline_text, convert_bytes, count_tokens

FIXTURE = Path(__file__).parent / "fixtures" / "sample.html"


def test_count_tokens_counts_text():
    assert count_tokens("") == 0
    assert count_tokens("hello world") >= 2


def test_html_keeps_content_and_uses_fewer_tokens():
    data = FIXTURE.read_bytes()
    result = convert_bytes("sample.html", data)

    assert "Quarterly Supply Review" in result.markdown
    assert "A-100" in result.markdown
    assert "Shipped" in result.markdown
    assert "420" in result.markdown
    assert "lot register" in result.markdown
    assert "https://example.com/lots" in result.markdown
    assert result.source_tokens is not None
    assert result.markdown_tokens < result.source_tokens
    assert result.savings_pct is not None
    assert result.savings_pct > 0


def test_office_xml_baseline_keeps_document_xml():
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "word/document.xml",
            "<w:document><w:t>Lot A-100 shipped</w:t></w:document>",
        )
        archive.writestr("word/styles.xml", "<w:styles>ignore</w:styles>")

    text = baseline_text(".docx", buffer.getvalue())

    assert text is not None
    assert "<w:document>" in text
    assert "Lot A-100 shipped" in text
    assert "ignore" not in text


def test_image_has_no_text_baseline():
    assert baseline_text(".png", b"not-an-image") is None


def test_rejects_unknown_extension():
    with pytest.raises(ConversionError):
        convert_bytes("notes.txt", b"hello")


def test_rejects_oversize_file(monkeypatch):
    monkeypatch.setattr("app.converter.MAX_BYTES", 4)
    with pytest.raises(ConversionError):
        convert_bytes("sample.html", b"12345")
