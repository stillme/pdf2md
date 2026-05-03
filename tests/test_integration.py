"""End-to-end integration tests for Phase 1 (fast tier)."""

import json
import pytest
from pdfvault import convert, Document


def test_full_pipeline_fast(sample_pdf_bytes):
    doc = convert(sample_pdf_bytes, tier="fast")
    assert isinstance(doc, Document)
    assert doc.metadata.pages == 2
    assert doc.processing_time_ms > 0
    assert doc.confidence > 0.5
    assert len(doc.sections) > 0
    assert len(doc.tables) >= 1
    assert len(doc.markdown) > 200


def test_full_pipeline_from_file(sample_pdf_path):
    doc = convert(str(sample_pdf_path), tier="fast")
    assert doc.metadata.pages == 2
    assert len(doc.markdown) > 200


def test_save_and_load_json(sample_pdf_bytes, tmp_path):
    doc = convert(sample_pdf_bytes, tier="fast")
    json_path = tmp_path / "doc.json"
    doc.save_json(str(json_path))
    data = json.loads(json_path.read_text())
    assert data["metadata"]["pages"] == 2
    assert len(data["sections"]) > 0
    assert len(data["tables"]) >= 1


def test_page_confidences(sample_pdf_bytes):
    doc = convert(sample_pdf_bytes, tier="fast")
    assert len(doc.page_confidences) == 2
    for c in doc.page_confidences:
        assert 0.0 <= c <= 1.0


def test_full_pipeline_deep_with_mock_vlm(sample_pdf_bytes):
    from unittest.mock import MagicMock, patch
    import json
    from pdfvault.extractors.pypdfium_ext import PypdfiumExtractor
    from pdfvault.extractors.pdfplumber_ext import PdfplumberExtractor
    mock_provider = MagicMock()
    mock_provider.name = "gemini"
    mock_provider.complete_sync.return_value = json.dumps({
        "status": "pass", "confidence": 0.92, "corrections": [],
    })
    # Exclude marker so the test only exercises VLM logic, not the surya ML model
    with patch("pdfvault.core._get_vlm_provider", return_value=mock_provider), \
         patch("pdfvault.extractors.get_available_extractors",
               return_value=[PypdfiumExtractor(), PdfplumberExtractor()]):
        doc = convert(sample_pdf_bytes, tier="deep", figures="caption")
        assert doc.metadata.pages == 2
        assert doc.confidence > 0


def test_full_pipeline_auto_tier(sample_pdf_bytes):
    doc = convert(sample_pdf_bytes, tier="auto")
    assert doc.metadata.pages == 2
    assert len(doc.markdown) > 100


def test_metadata_extraction(sample_pdf_bytes):
    doc = convert(sample_pdf_bytes, tier="fast")
    assert doc.metadata.title is not None
    assert "Sample" in doc.metadata.title or "Research" in doc.metadata.title


def test_scanned_pdf_routes_to_vlm(scanned_pdf_bytes):
    """End-to-end: scanned PDF + standard tier should fire the VLM extractor.

    Verifies the full triage -> route -> extract chain on a synthetic
    image-only PDF. The VLM provider is mocked so this test never spends
    subscription / API quota — but it does assert the provider is called
    with a PNG image payload, which is the contract the real
    ``VLMExtractor`` relies on.
    """
    from unittest.mock import MagicMock, patch

    canned_markdown = (
        "# SCANNED SAMPLE DOCUMENT\n\n"
        "## Abstract\n\n"
        "This page exists only as a raster image. There is no embedded "
        "text layer.\n"
    )

    mock_provider = MagicMock()
    mock_provider.name = "claude-cli"
    mock_provider.complete_sync.return_value = canned_markdown

    with patch("pdfvault.core._get_vlm_provider", return_value=mock_provider):
        doc = convert(scanned_pdf_bytes, tier="standard", provider="claude-cli")

    # The VLM extractor must have actually fired (not just been routed).
    assert mock_provider.complete_sync.called, (
        "VLM extractor was not invoked — routing or extraction broke."
    )
    # First call should have an ``image=`` kwarg with PNG bytes from the
    # rendered scanned page.
    call_kwargs = mock_provider.complete_sync.call_args_list[0].kwargs
    assert "image" in call_kwargs and isinstance(call_kwargs["image"], bytes)
    assert call_kwargs["image"].startswith(b"\x89PNG"), (
        "VLM was not handed a PNG render of the scanned page."
    )

    # The assembled document should reflect the canned VLM output.
    assert doc.engine_used == "vlm", (
        f"Expected engine_used='vlm', got {doc.engine_used!r}. Routing "
        "may have fallen back to a text extractor."
    )
    assert "SCANNED SAMPLE DOCUMENT" in doc.markdown
