"""Tests for VLM provider protocol and registry."""

from pdf2md.providers.base import VLMProvider, VerifyResult
from pdf2md.providers.registry import detect_providers, get_provider


def test_verify_result_pass():
    r = VerifyResult(status="pass", confidence=0.95, corrections=[])
    assert r.status == "pass"


def test_verify_result_fail():
    r = VerifyResult(
        status="fail", confidence=0.4,
        corrections=[{"region": "table1", "problem": "wrong columns", "fix": "corrected table"}],
    )
    assert len(r.corrections) == 1


def test_detect_providers_returns_list():
    providers = detect_providers()
    assert isinstance(providers, list)
    for p in providers:
        assert "name" in p
        assert "available" in p


def test_get_provider_returns_none_for_unknown():
    provider = get_provider("nonexistent/model")
    assert provider is None
