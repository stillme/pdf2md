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


def test_convert_standard_tier_with_mock_vlm(sample_pdf_bytes):
    from unittest.mock import MagicMock, patch
    mock_provider = MagicMock()
    mock_provider.name = "gemini"
    mock_provider.complete_sync.return_value = "A figure showing experimental results."
    with patch("pdf2md.core._get_vlm_provider", return_value=mock_provider):
        doc = convert(sample_pdf_bytes, tier="standard", figures="describe")
        assert doc.tier_used == "standard"


def test_convert_standard_without_vlm_falls_back(sample_pdf_bytes):
    from unittest.mock import patch
    with patch("pdf2md.core._get_vlm_provider", return_value=None):
        doc = convert(sample_pdf_bytes, tier="standard")
        assert doc.metadata.pages == 2
        assert len(doc.markdown) > 100


# --- Bug 4: Deep tier preserves title after reassembly ---

def test_deep_tier_preserves_title(sample_pdf_bytes):
    import json
    from unittest.mock import MagicMock, patch
    import pdf2md
    mock_provider = MagicMock()
    mock_provider.name = "test"
    mock_provider.complete_sync.return_value = json.dumps({"status": "pass", "confidence": 0.95, "corrections": []})
    with patch("pdf2md.core._get_vlm_provider", return_value=mock_provider):
        doc = pdf2md.convert(sample_pdf_bytes, tier="deep")
        assert doc.metadata.title is not None, "Title should be preserved after deep tier reassembly"
