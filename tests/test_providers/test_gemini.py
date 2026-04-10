"""Tests for Gemini VLM provider."""
from unittest.mock import patch, MagicMock
from pdf2md.providers.gemini import GeminiProvider


def test_gemini_provider_name():
    p = GeminiProvider(model="gemini-2.0-flash")
    assert p.name == "gemini"


def test_gemini_complete_sync_with_mock():
    p = GeminiProvider(model="gemini-2.0-flash")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": "Extracted text from image."}]}}]
    }
    with patch("httpx.post", return_value=mock_response):
        result = p.complete_sync("Describe this image", image=b"fake_image_bytes")
        assert "Extracted text" in result


def test_gemini_complete_sync_text_only():
    p = GeminiProvider(model="gemini-2.0-flash")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": "Response without image."}]}}]
    }
    with patch("httpx.post", return_value=mock_response):
        result = p.complete_sync("What is 2+2?")
        assert "Response" in result
