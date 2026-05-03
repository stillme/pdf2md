"""Tests for VLM direct extractor."""
import pytest
from unittest.mock import MagicMock
from pdfvault.extractors.vlm_ext import VLMExtractor


def test_vlm_extractor_name():
    mock_provider = MagicMock()
    mock_provider.name = "gemini"
    ext = VLMExtractor(provider=mock_provider)
    assert ext.name == "vlm"


def test_vlm_extractor_capabilities():
    ext = VLMExtractor(provider=MagicMock())
    assert "text" in ext.capabilities
    assert "tables" in ext.capabilities
    assert "layout" in ext.capabilities
    assert "ocr" in ext.capabilities


def test_vlm_extract_page(sample_pdf_bytes):
    mock_provider = MagicMock()
    mock_provider.complete_sync.return_value = (
        "# Introduction\n\nThis is the introduction section.\n\n"
        "| Condition | Mean | SD |\n|---|---|---|\n| Control | 12.3 | 2.1 |\n"
    )
    ext = VLMExtractor(provider=mock_provider)
    page = ext.extract_page(sample_pdf_bytes, 0)
    assert page.page_number == 0
    assert "Introduction" in page.text
    assert page.confidence >= 0.6
    mock_provider.complete_sync.assert_called_once()
    call_args = mock_provider.complete_sync.call_args
    # Verify image was passed
    assert call_args.kwargs.get("image") is not None or (len(call_args.args) > 1 and call_args.args[1] is not None)
