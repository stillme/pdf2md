"""Tests for the CLI."""

from unittest.mock import patch

import pytest
from click.testing import CliRunner
from pdfvault.cli import main
from pdfvault.document import Document, Metadata


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


def test_convert_writes_figure_index_sidecar(runner, sample_pdf_path, tmp_path):
    out = tmp_path / "output.md"
    figures_json = tmp_path / "figures.json"
    result = runner.invoke(
        main,
        [
            "convert",
            str(sample_pdf_path),
            "-o",
            str(out),
            "--figures-json",
            str(figures_json),
        ],
    )
    assert result.exit_code == 0
    assert figures_json.exists()
    assert "pdfvault.figure_index.v1" in figures_json.read_text()


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


def test_batch_help(runner):
    result = runner.invoke(main, ["batch", "--help"])
    assert result.exit_code == 0
    assert "--output-dir" in result.output
    assert "--concurrency" in result.output
    assert "--checkpoint" in result.output
    assert "--no-resume" in result.output


def test_batch_smoke(runner, tmp_path):
    # Create two minimal "pdfs" — convert is mocked, contents don't matter.
    in_dir = tmp_path / "in"
    in_dir.mkdir()
    for name in ["one.pdf", "two.pdf"]:
        (in_dir / name).write_bytes(b"%PDF-1.4\n%fake")
    out_dir = tmp_path / "out"

    fake_doc = Document(markdown="# Mock", metadata=Metadata(pages=1))

    with patch("pdfvault.core.convert", return_value=fake_doc) as mock_convert:
        result = runner.invoke(
            main,
            ["batch", str(in_dir), "--output-dir", str(out_dir), "--tier", "fast"],
        )

    assert result.exit_code == 0, result.output
    assert mock_convert.call_count == 2
    assert "Batch Summary" in result.output
    assert "Completed: 2" in result.output
    assert (out_dir / "one.md").exists()
    assert (out_dir / "two.md").exists()
    assert (out_dir / ".pdfvault-batch.json").exists()


def test_batch_no_pdfs_found(runner, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    out = tmp_path / "out"
    result = runner.invoke(
        main, ["batch", str(empty), "--output-dir", str(out)],
    )
    assert result.exit_code != 0
    assert "No PDFs found" in result.output
