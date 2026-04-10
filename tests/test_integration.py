"""End-to-end integration tests for Phase 1 (fast tier)."""

import json
import pytest
from pdf2md import convert, Document


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
