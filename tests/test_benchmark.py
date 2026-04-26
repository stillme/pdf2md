"""Tests for benchmark runner (unit tests only, no downloads)."""

from unittest.mock import MagicMock, patch

from pdf2md.benchmarks.runner import BenchmarkResult, print_summary, BENCHMARK_PAPERS


def test_benchmark_papers_defined():
    assert len(BENCHMARK_PAPERS) >= 3
    for p in BENCHMARK_PAPERS:
        assert "name" in p
        # Each paper must have either a URL or a local_filename basename
        has_url = p.get("url", "").startswith("https://")
        has_local = bool(p.get("local_filename", ""))
        assert has_url or has_local, (
            f"Paper {p['name']} needs a url or local_filename"
        )
        # local_filename must be a basename (no path separators), so it stays
        # portable across machines.
        if has_local:
            local = p["local_filename"]
            assert "/" not in local and "\\" not in local, (
                f"Paper {p['name']} local_filename must be a basename"
            )


def test_benchmark_result_creation():
    r = BenchmarkResult(
        name="test", category="test", pages=10, expected_pages=10,
        title_extracted=True, title="Test Paper", sections_found=5,
        section_names=["Intro", "Methods"], tables_found=2, figures_found=1,
        confidence=0.95, time_ms=500,
    )
    assert r.pages == 10
    assert r.title_extracted


def test_print_summary(capsys):
    results = [
        BenchmarkResult(
            name="paper1", category="ml", pages=10, expected_pages=10,
            title_extracted=True, title="Test", sections_found=5,
            section_names=[], tables_found=2, figures_found=0,
            confidence=0.95, time_ms=500,
        ),
    ]
    print_summary(results)
    captured = capsys.readouterr()
    assert "paper1" in captured.out
    assert "1/1" in captured.out


def test_benchmark_on_sample_pdf(sample_pdf_bytes):
    """Run benchmark on sample PDF (no network needed)."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = sample_pdf_bytes

    test_papers = [
        {
            "name": "sample",
            "url": "https://fake.url/paper.pdf",
            "expected_pages": 2,
            "has_tables": True,
            "has_math": False,
            "category": "test",
        },
    ]

    with patch("pdf2md.benchmarks.runner.httpx") as mock_httpx:
        mock_httpx.get.return_value = mock_response
        from pdf2md.benchmarks.runner import run_benchmarks
        results = run_benchmarks(papers=test_papers, tier="fast")
        assert len(results) == 1
        assert results[0].pages == 2
        assert results[0].sections_found > 0
        assert results[0].error is None
