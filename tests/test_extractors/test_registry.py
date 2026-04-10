"""Tests for extractor protocol and registry."""

from pdf2md.extractors.base import Extractor, PageContent, ExtractionResult
from pdf2md.extractors import get_available_extractors


def test_page_content_creation():
    pc = PageContent(
        page_number=1, text="Hello world", tables=[], figures=[], confidence=0.9,
    )
    assert pc.page_number == 1
    assert pc.text == "Hello world"
    assert pc.confidence == 0.9


def test_extraction_result():
    er = ExtractionResult(
        pages=[PageContent(page_number=1, text="Page 1", tables=[], figures=[], confidence=0.9)],
        engine="test",
    )
    assert len(er.pages) == 1
    assert er.engine == "test"


def test_get_available_extractors():
    extractors = get_available_extractors()
    names = [e.name for e in extractors]
    assert "pypdfium2" in names
    assert "pdfplumber" in names
