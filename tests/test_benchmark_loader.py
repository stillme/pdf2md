"""Tests for the benchmark PDF loader's portable path resolution."""

from unittest.mock import MagicMock, patch

import pytest

from pdf2md.benchmarks import runner
from pdf2md.benchmarks.runner import _load_pdf


def test_local_filename_resolves_under_env_dir(tmp_path, monkeypatch, capsys):
    """A paper with a ``local_filename`` is resolved beneath
    ``$PDF2MD_BENCHMARK_DIR`` and its bytes are returned verbatim."""
    monkeypatch.setenv("PDF2MD_BENCHMARK_DIR", str(tmp_path))

    pdf_bytes = b"%PDF-1.4\n%fake-placeholder\n"
    (tmp_path / "paper.pdf").write_bytes(pdf_bytes)

    paper = {
        "name": "local-only",
        "local_filename": "paper.pdf",
        "url": "",
    }

    result = _load_pdf(paper)
    assert result == pdf_bytes

    out = capsys.readouterr().out
    assert "Loaded" in out
    assert str(tmp_path) in out


def test_local_filename_falls_through_to_url_when_missing(
    tmp_path, monkeypatch, capsys,
):
    """When the local file is missing but a URL is configured, the loader
    falls through and downloads from the URL."""
    monkeypatch.setenv("PDF2MD_BENCHMARK_DIR", str(tmp_path))
    # Deliberately do NOT create the local file.

    pdf_bytes = b"%PDF-1.4\nfetched-from-url\n"
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = pdf_bytes

    paper = {
        "name": "fallback-url",
        "local_filename": "missing.pdf",
        "url": "https://example.invalid/paper.pdf",
    }

    with patch.object(runner, "httpx") as mock_httpx:
        mock_httpx.get.return_value = mock_response
        result = _load_pdf(paper)

        # Confirm the URL path was actually used.
        assert mock_httpx.get.call_count == 1
        called_url = mock_httpx.get.call_args[0][0]
        assert called_url == "https://example.invalid/paper.pdf"

    assert result == pdf_bytes
    assert "Downloaded" in capsys.readouterr().out


def test_skip_when_neither_path_nor_url_works(tmp_path, monkeypatch, capsys):
    """Loader returns ``None`` and prints a clear skip message when there is
    no usable local file and no URL."""
    monkeypatch.setenv("PDF2MD_BENCHMARK_DIR", str(tmp_path))

    paper = {
        "name": "nowhere",
        "local_filename": "missing.pdf",
        "url": "",
    }

    result = _load_pdf(paper)
    assert result is None

    out = capsys.readouterr().out
    assert "SKIP" in out
    assert "nowhere" in out


def test_skip_when_neither_path_nor_url_works_raises_when_strict(
    tmp_path, monkeypatch,
):
    """With ``skip_errors=False`` the loader raises instead of returning
    ``None``."""
    monkeypatch.setenv("PDF2MD_BENCHMARK_DIR", str(tmp_path))

    paper = {
        "name": "nowhere",
        "local_filename": "missing.pdf",
        "url": "",
    }

    with pytest.raises(FileNotFoundError):
        _load_pdf(paper, skip_errors=False)
