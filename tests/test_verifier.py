"""Tests for the agentic verify-correct loop."""
from unittest.mock import MagicMock
import json
from pdf2md.verifier import verify_page, run_verify_loop
from pdf2md.providers.base import VerifyResult


def test_verify_pass():
    mock_provider = MagicMock()
    mock_provider.complete_sync.return_value = json.dumps({
        "status": "pass", "confidence": 0.95, "corrections": [],
    })
    result = verify_page(page_image=b"fake_image", extracted_markdown="# Introduction\n\nSome text.", provider=mock_provider)
    assert result.status == "pass"
    assert result.confidence >= 0.9


def test_verify_fail_with_corrections():
    mock_provider = MagicMock()
    mock_provider.complete_sync.return_value = json.dumps({
        "status": "fail", "confidence": 0.4,
        "corrections": [{"region": "paragraph2", "problem": "Missing sentence", "fix": "Added missing text."}],
    })
    result = verify_page(page_image=b"fake_image", extracted_markdown="# Results\n\nIncomplete text.", provider=mock_provider)
    assert result.status == "fail"
    assert len(result.corrections) == 1


def test_verify_handles_non_json_response():
    mock_provider = MagicMock()
    mock_provider.complete_sync.return_value = "This looks correct to me."
    result = verify_page(page_image=b"fake_image", extracted_markdown="Some text.", provider=mock_provider)
    assert result.status == "pass"
    assert result.confidence >= 0.5


def test_verify_handles_provider_error():
    mock_provider = MagicMock()
    mock_provider.complete_sync.side_effect = Exception("API error")
    result = verify_page(page_image=b"fake_image", extracted_markdown="Some text.", provider=mock_provider)
    assert result.status == "pass"
    assert result.confidence <= 0.5


def test_verify_loop_passes_immediately():
    mock_provider = MagicMock()
    mock_provider.complete_sync.return_value = json.dumps({
        "status": "pass", "confidence": 0.95, "corrections": [],
    })
    markdown, confidence = run_verify_loop(b"fake_image", "Good markdown.", mock_provider, max_rounds=2)
    assert confidence >= 0.9
    assert markdown == "Good markdown."
    assert mock_provider.complete_sync.call_count == 1


def test_verify_loop_corrects_and_re_verifies():
    mock_provider = MagicMock()
    responses = [
        json.dumps({"status": "fail", "confidence": 0.4, "corrections": [{"region": "p1", "problem": "typo", "fix": "fixed"}]}),
        json.dumps({"status": "pass", "confidence": 0.9, "corrections": []}),
    ]
    mock_provider.complete_sync.side_effect = responses
    markdown, confidence = run_verify_loop(b"fake_image", "Some text with typo.", mock_provider, max_rounds=2)
    assert confidence >= 0.4
    assert mock_provider.complete_sync.call_count == 2
