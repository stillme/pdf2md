"""Tests for the batch quality report.

Each anomaly heuristic gets a positive case (the flag fires when it
should) and a negative case (the flag does NOT fire on healthy
output). Heuristics were tuned against the real ``test_pdfs/``
corpus, so the test inputs mirror the shapes of real failure modes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pdf2md.batch import BatchSummary, PaperResult
from pdf2md.quality_report import (
    analyze_paper,
    build_quality_report,
    format_report_markdown,
    write_quality_report,
)


# --- Helpers ----------------------------------------------------------------


def _write_doc(
    tmp_path: Path,
    name: str,
    *,
    pages: int = 10,
    sections: int = 8,
    figures: int = 2,
    tables: int = 1,
    bibliography: int = 25,
    confidence: float = 1.0,
    warnings: list[str] | None = None,
    markdown: str = "",
) -> PaperResult:
    """Write a fake JSON doc and return the matching ``PaperResult``."""
    json_path = tmp_path / f"{name}.json"
    md_path = tmp_path / f"{name}.md"
    doc = {
        "metadata": {"pages": pages, "title": "Test Paper", "authors": []},
        "sections": [{"level": 1, "title": f"S{i}", "content": "", "page": 1} for i in range(sections)],
        "figures": [{"id": f"fig{i}", "page": 1} for i in range(figures)],
        "tables": [{"id": f"tab{i}"} for i in range(tables)],
        "bibliography": [{"id": f"ref-{i}"} for i in range(bibliography)],
        "warnings": warnings or [],
        "confidence": confidence,
        "markdown": markdown or "Some body text.",
    }
    json_path.write_text(json.dumps(doc))
    md_path.write_text(doc["markdown"])
    return PaperResult(
        path=str(tmp_path / f"{name}.pdf"),
        status="completed",
        duration_s=5.0,
        output_md=str(md_path),
        output_json=str(json_path),
    )


# --- Per-paper analysis -----------------------------------------------------


def test_clean_paper_has_no_flags(tmp_path):
    result = _write_doc(tmp_path, "clean")
    pq = analyze_paper(result)
    assert pq is not None
    assert pq.flags == []
    assert pq.pages == 10


def test_low_confidence_flagged(tmp_path):
    result = _write_doc(tmp_path, "lowconf", confidence=0.7)
    pq = analyze_paper(result)
    assert "low_confidence" in pq.flags


def test_no_references_flagged_on_real_paper(tmp_path):
    """Any paper >5 pages with 0 refs lost the bibliography entirely."""
    result = _write_doc(tmp_path, "noref", pages=15, bibliography=0)
    pq = analyze_paper(result)
    assert "no_references" in pq.flags


def test_no_references_not_flagged_on_short_pdf(tmp_path):
    """A 3-page handout legitimately may have no references."""
    result = _write_doc(tmp_path, "shorter", pages=3, bibliography=0)
    pq = analyze_paper(result)
    assert "no_references" not in pq.flags


def test_few_references_flagged_when_count_low_for_paper_size(tmp_path):
    """A 30-page paper with only 5 refs likely missed most of the
    bibliography section."""
    result = _write_doc(tmp_path, "fewrefs", pages=30, bibliography=5)
    pq = analyze_paper(result)
    assert "few_references" in pq.flags


def test_no_figures_flagged_when_body_mentions_figures(tmp_path):
    """0 figures + body text mentioning Fig. X = extractor missed them."""
    result = _write_doc(
        tmp_path, "nofig",
        pages=20, figures=0,
        markdown="As shown in Fig. 3 the result was clear.",
    )
    pq = analyze_paper(result)
    assert "no_figures_with_mentions" in pq.flags


def test_no_figures_not_flagged_when_body_has_no_figure_mentions(tmp_path):
    """Some review papers genuinely have no figures — don't false-flag."""
    result = _write_doc(
        tmp_path, "nofigreview",
        pages=20, figures=0,
        markdown="A purely textual review of the literature.",
    )
    pq = analyze_paper(result)
    assert "no_figures_with_mentions" not in pq.flags


def test_no_tables_flagged_when_body_mentions_tables(tmp_path):
    """The interesting case: 0 tables AND body says 'Table 1' — extractor missed something."""
    result = _write_doc(
        tmp_path, "notab", pages=40, tables=0,
        markdown="As shown in Table 1 the cohort had 200 patients.",
    )
    pq = analyze_paper(result)
    assert "no_tables_with_mentions" in pq.flags


def test_no_tables_not_flagged_when_body_has_no_table_mentions(tmp_path):
    """Real example: Nature s41586-024-08216-z genuinely has zero tables.
    Body text never says ``Table N`` — flagging it as a miss is a false
    positive that drowns the signal in the batch report."""
    result = _write_doc(
        tmp_path, "notabnomentions", pages=40, tables=0,
        markdown="A long paper that legitimately contains no tabular data.",
    )
    pq = analyze_paper(result)
    assert "no_tables_with_mentions" not in pq.flags


def test_no_tables_not_flagged_on_short_paper(tmp_path):
    result = _write_doc(
        tmp_path, "shortnotab", pages=15, tables=0,
        markdown="See Table 1.",
    )
    pq = analyze_paper(result)
    assert "no_tables_with_mentions" not in pq.flags


def test_few_sections_flagged(tmp_path):
    result = _write_doc(tmp_path, "fewsec", pages=25, sections=2)
    pq = analyze_paper(result)
    assert "few_sections" in pq.flags


def test_warnings_flag_fires(tmp_path):
    result = _write_doc(
        tmp_path, "withwarn",
        warnings=["pymupdf not installed", "verify failed"],
    )
    pq = analyze_paper(result)
    assert "has_warnings" in pq.flags


def test_very_long_document_skips_subflags(tmp_path):
    """Books / dissertations don't fit research-paper heuristics — flag
    once as long, skip the noisy missing-figure / missing-table flags
    so the report doesn't drown in false positives on a single 361-page
    SSRN PDF."""
    result = _write_doc(
        tmp_path, "longdoc",
        pages=361, sections=200, figures=0, tables=0, bibliography=10,
    )
    pq = analyze_paper(result)
    assert "very_long_document" in pq.flags
    assert "no_figures_with_mentions" not in pq.flags
    assert "no_tables_with_mentions" not in pq.flags
    assert "no_references" not in pq.flags
    assert "few_sections" not in pq.flags
    assert "long document" in pq.note


def test_failed_paper_excluded_from_quality_report(tmp_path):
    failed = PaperResult(
        path=str(tmp_path / "broken.pdf"),
        status="failed",
        error="Invalid PDF",
        duration_s=0.1,
    )
    pq = analyze_paper(failed)
    assert pq is None


def test_unreadable_json_flagged(tmp_path):
    """If the saved JSON disappears or is corrupted between conversion
    and report generation we still want to know the paper exists."""
    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{ not valid json")
    result = PaperResult(
        path=str(tmp_path / "bad.pdf"),
        status="completed",
        duration_s=2.0,
        output_md=str(tmp_path / "bad.md"),
        output_json=str(bad_json),
    )
    pq = analyze_paper(result)
    assert pq is not None
    assert "json_unreadable" in pq.flags


# --- Top-level report -------------------------------------------------------


def test_build_quality_report_aggregates_across_papers(tmp_path):
    summary = BatchSummary(
        total=3, completed=3, failed=0, skipped=0, total_duration_s=10.0,
        results=[
            _write_doc(tmp_path, "good"),
            _write_doc(tmp_path, "noref", pages=15, bibliography=0),
            _write_doc(tmp_path, "lowconf", confidence=0.7),
        ],
    )
    report = build_quality_report(summary)
    assert report.total == 3
    assert report.flagged == 2
    assert report.flag_counts.get("no_references") == 1
    assert report.flag_counts.get("low_confidence") == 1


def test_format_markdown_lists_flagged_first_then_clean(tmp_path):
    summary = BatchSummary(
        total=2, completed=2,
        results=[
            _write_doc(tmp_path, "good"),
            _write_doc(tmp_path, "noref", pages=15, bibliography=0),
        ],
    )
    report = build_quality_report(summary)
    md = format_report_markdown(report)
    assert "Batch Quality Report" in md
    assert "Papers needing review" in md
    assert "noref" in md
    # Clean papers section appears AFTER the flagged section so the
    # reader sees anomalies first.
    assert md.index("Papers needing review") < md.index("Clean papers")


def test_write_quality_report_creates_md_and_json(tmp_path):
    summary = BatchSummary(
        total=1, completed=1,
        results=[_write_doc(tmp_path, "ok")],
    )
    report = write_quality_report(summary, tmp_path)
    assert (tmp_path / "report.md").exists()
    assert (tmp_path / "report.json").exists()
    # Round-trip the JSON to confirm it's valid + matches the report.
    on_disk = json.loads((tmp_path / "report.json").read_text())
    assert on_disk["total"] == report.total


def test_skipped_papers_with_existing_json_are_analyzed(tmp_path):
    """Resumed batches should still get a complete quality report —
    the JSON written on the first run is the source of truth."""
    result = _write_doc(tmp_path, "cached")
    # Mark this result as skipped (resume-from-checkpoint case).
    result = result.model_copy(update={"status": "skipped"})
    pq = analyze_paper(result)
    assert pq is not None
    assert pq.pages == 10
