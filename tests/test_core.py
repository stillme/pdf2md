"""Tests for the core convert() orchestrator."""

import pytest
from pdf2md import convert, Document
from pdf2md.config import Tier


def test_convert_file_path(sample_pdf_path):
    doc = convert(str(sample_pdf_path))
    assert isinstance(doc, Document)
    assert doc.metadata.pages == 2
    assert "Introduction" in doc.markdown
    assert doc.processing_time_ms > 0


def test_convert_bytes(sample_pdf_bytes):
    doc = convert(sample_pdf_bytes)
    assert isinstance(doc, Document)
    assert doc.metadata.pages == 2


def test_convert_fast_tier(sample_pdf_bytes):
    doc = convert(sample_pdf_bytes, tier="fast")
    assert doc.tier_used == "fast"


def test_convert_extracts_sections(sample_pdf_bytes):
    doc = convert(sample_pdf_bytes, tier="fast")
    section_titles = [s.title for s in doc.sections]
    assert any("Introduction" in t for t in section_titles) or any("Results" in t for t in section_titles)


def test_convert_extracts_tables(sample_pdf_bytes):
    doc = convert(sample_pdf_bytes, tier="fast")
    assert len(doc.tables) >= 1
    assert "Condition" in doc.tables[0].headers


def test_convert_has_confidence(sample_pdf_bytes):
    doc = convert(sample_pdf_bytes, tier="fast")
    assert doc.confidence > 0
    assert len(doc.page_confidences) == 2


def test_convert_invalid_input():
    with pytest.raises(ValueError):
        convert(b"not a pdf")


def test_convert_file_not_found():
    with pytest.raises(FileNotFoundError):
        convert("/nonexistent/file.pdf")


def test_convert_save_markdown(sample_pdf_bytes, tmp_path):
    doc = convert(sample_pdf_bytes, tier="fast")
    out = tmp_path / "output.md"
    doc.save_markdown(str(out))
    content = out.read_text()
    assert len(content) > 100
