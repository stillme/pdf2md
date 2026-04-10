"""Tests for the CLI."""

import pytest
from click.testing import CliRunner
from pdf2md.cli import main


@pytest.fixture
def runner():
    return CliRunner()


def test_convert_file(runner, sample_pdf_path):
    result = runner.invoke(main, ["convert", str(sample_pdf_path)])
    assert result.exit_code == 0
    assert "Introduction" in result.output or "Sample" in result.output


def test_convert_to_file(runner, sample_pdf_path, tmp_path):
    out = tmp_path / "output.md"
    result = runner.invoke(main, ["convert", str(sample_pdf_path), "-o", str(out)])
    assert result.exit_code == 0
    assert out.exists()
    assert len(out.read_text()) > 100


def test_convert_with_tier(runner, sample_pdf_path):
    result = runner.invoke(main, ["convert", str(sample_pdf_path), "--tier", "fast"])
    assert result.exit_code == 0


def test_convert_invalid_file(runner):
    result = runner.invoke(main, ["convert", "/nonexistent.pdf"])
    assert result.exit_code != 0


def test_info_command(runner):
    result = runner.invoke(main, ["info"])
    assert result.exit_code == 0
    assert "pypdfium2" in result.output
    assert "pdfplumber" in result.output


def test_version(runner):
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output
