"""Tests for pdfvault configuration."""

import os
from pdfvault.config import Config, Tier, FigureMode


def test_default_config():
    c = Config()
    assert c.tier == Tier.AUTO
    assert c.figures == FigureMode.CAPTION
    assert c.verify is True
    assert c.provider is None
    assert c.max_concurrent_pages == 4
    assert c.max_verify_rounds == 2
    assert c.timeout_per_page == 60


def test_config_from_tier_string():
    c = Config(tier="deep")
    assert c.tier == Tier.DEEP


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("PDFVAULT_TIER", "standard")
    monkeypatch.setenv("PDFVAULT_FIGURES", "describe")
    monkeypatch.setenv("PDFVAULT_PROVIDER", "gemini/gemini-2.0-flash")
    c = Config()
    assert c.tier == Tier.STANDARD
    assert c.figures == FigureMode.DESCRIBE
    assert c.provider == "gemini/gemini-2.0-flash"


def test_tier_enum_values():
    assert Tier.FAST.value == "fast"
    assert Tier.STANDARD.value == "standard"
    assert Tier.DEEP.value == "deep"
    assert Tier.AUTO.value == "auto"


def test_figure_mode_enum():
    assert FigureMode.SKIP.value == "skip"
    assert FigureMode.CAPTION.value == "caption"
    assert FigureMode.DESCRIBE.value == "describe"
    assert FigureMode.EXTRACT.value == "extract"
