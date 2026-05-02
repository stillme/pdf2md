"""Per-paper quality flags for batch runs.

At corpus scale a user can't read every output. This module turns a
``BatchSummary`` plus the per-paper JSON files it wrote into a single
report that flags anomalies — papers where the conversion looks
suspicious based on shape (zero figures on a 30-page paper, zero
references on anything over five pages, broken section detection,
etc.).

The heuristics are deliberately conservative: every flag corresponds
to a real failure mode observed on the test corpus. False positives
are tolerated as long as they're rare; false negatives are the
expensive class because they hide bad output in the long tail.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel, Field

from pdf2md.batch import BatchSummary, PaperResult

logger = logging.getLogger(__name__)


# --- Heuristic thresholds ---------------------------------------------------
#
# Tuned against the test_pdfs/ corpus dry-run. Paper-class branches
# (e.g. "long doc" for >200 pages) avoid noisy flags on dissertations
# and books that legitimately have different shapes than research
# articles.

_LOW_CONFIDENCE = 0.85

_LONG_PAPER_PAGES = 10        # threshold for expecting figures + sections
_NO_TABLES_PAGES = 30         # only flag missing tables on substantial papers
_FEW_REFS_PAGES = 5           # any paper with body content should have refs
_FEW_REFS_THRESHOLD = 10      # below this, the bib parser likely missed a section
_FEW_SECTIONS_PAGES = 10
_FEW_SECTIONS_THRESHOLD = 5
_VERY_LONG_DOC_PAGES = 200    # books / dissertations get a separate note
_SLOW_FAST_TIER_S = 60.0      # fast tier should rarely exceed this on a single paper


@dataclass(frozen=True)
class QualityFlag:
    """A single anomaly description.

    ``code`` is a stable identifier callers can filter or alert on
    programmatically (``"no_figures"``, ``"low_confidence"``).
    ``message`` is the human-readable form used in the markdown
    report.
    """

    code: str
    message: str


class PaperQuality(BaseModel):
    """Per-paper quality summary derived from the saved JSON output."""

    path: str
    pages: int = 0
    sections: int = 0
    figures: int = 0
    tables: int = 0
    references: int = 0
    confidence: float = 0.0
    warnings: int = 0
    duration_s: float = 0.0
    flags: list[str] = Field(default_factory=list)
    flag_messages: list[str] = Field(default_factory=list)
    note: str = ""  # one-line context (e.g. "long document, 361 pages")


class QualityReport(BaseModel):
    """Top-level report for a batch run."""

    total: int = 0
    flagged: int = 0
    failed: int = 0
    skipped: int = 0
    flag_counts: dict[str, int] = Field(default_factory=dict)
    papers: list[PaperQuality] = Field(default_factory=list)


# --- Per-paper analysis -----------------------------------------------------


def _load_doc_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("could not read %s: %s", path, exc)
        return None


def _has_figure_mentions(markdown: str) -> bool:
    """True if the body text references figures.

    A paper with body figure mentions but zero extracted figures is the
    interesting case — pdfplumber/pymupdf missed the visuals. A paper
    with no figure mentions either has no figures or is a no-figure
    format (review without panels), so we should not flag it.
    """
    if not markdown:
        return False
    lower = markdown.lower()
    return ("fig. " in lower) or ("figure " in lower)


_TABLE_MENTION_RE = re.compile(r"\bTable\s+\d+\b")


def _has_table_mentions(markdown: str) -> bool:
    """True if the body text references numbered tables.

    Symmetric reasoning to figure-mention detection: a long paper with
    zero extracted tables AND no body text saying ``Table N`` legitimately
    has no tables. Some life-science papers (Nature ``s41586-024-08216-z``
    is a real example) really don't have any — flagging them as a
    failure is a false positive that drowns the signal in the report.
    """
    if not markdown:
        return False
    return bool(_TABLE_MENTION_RE.search(markdown))


def analyze_paper(result: PaperResult) -> PaperQuality | None:
    """Return a :class:`PaperQuality` for one converted paper.

    Returns ``None`` for failed conversions (those are tracked at the
    batch level). Skipped papers are analysed if the prior JSON is
    still on disk so resumed batches still get a full report.
    """
    if result.status == "failed":
        return None
    if not result.output_json:
        return None

    doc = _load_doc_json(Path(result.output_json))
    if doc is None:
        return PaperQuality(
            path=result.path,
            duration_s=result.duration_s,
            flags=["json_unreadable"],
            flag_messages=["output JSON could not be read"],
        )

    pages = int(doc.get("metadata", {}).get("pages", 0) or 0)
    sections = len(doc.get("sections", []) or [])
    figures = len(doc.get("figures", []) or [])
    tables = len(doc.get("tables", []) or [])
    references = len(doc.get("bibliography", []) or [])
    confidence = float(doc.get("confidence", 0.0) or 0.0)
    warnings = doc.get("warnings", []) or []
    markdown = doc.get("markdown", "") or ""

    flags: list[QualityFlag] = []

    if pages >= _VERY_LONG_DOC_PAGES:
        # Books/dissertations skew every other heuristic; surface the
        # long-doc note up front and skip the noisy sub-flags below.
        flags.append(QualityFlag(
            "very_long_document",
            f"{pages} pages — likely book / dissertation, manual review recommended",
        ))
        note = f"long document, {pages} pages"
    else:
        note = ""
        if confidence < _LOW_CONFIDENCE:
            flags.append(QualityFlag(
                "low_confidence",
                f"confidence {confidence:.2f} (< {_LOW_CONFIDENCE})",
            ))
        if pages > _LONG_PAPER_PAGES and figures == 0 and _has_figure_mentions(markdown):
            flags.append(QualityFlag(
                "no_figures_with_mentions",
                "0 figures extracted but body text references figures — "
                "likely vector graphics or extractor miss",
            ))
        if (
            pages > _NO_TABLES_PAGES
            and tables == 0
            and _has_table_mentions(markdown)
        ):
            flags.append(QualityFlag(
                "no_tables_with_mentions",
                "0 tables extracted but body text references Table N — "
                "likely table extractor miss",
            ))
        if pages > _FEW_REFS_PAGES and references == 0:
            flags.append(QualityFlag(
                "no_references",
                "0 references parsed — bibliography section likely missed",
            ))
        elif pages > _LONG_PAPER_PAGES and 0 < references < _FEW_REFS_THRESHOLD:
            flags.append(QualityFlag(
                "few_references",
                f"only {references} references parsed on a {pages}-page paper",
            ))
        if pages > _FEW_SECTIONS_PAGES and sections < _FEW_SECTIONS_THRESHOLD:
            flags.append(QualityFlag(
                "few_sections",
                f"only {sections} sections detected on a {pages}-page paper",
            ))

    if warnings:
        flags.append(QualityFlag(
            "has_warnings",
            f"{len(warnings)} runtime warning(s) recorded",
        ))

    return PaperQuality(
        path=result.path,
        pages=pages,
        sections=sections,
        figures=figures,
        tables=tables,
        references=references,
        confidence=confidence,
        warnings=len(warnings),
        duration_s=result.duration_s,
        flags=[f.code for f in flags],
        flag_messages=[f.message for f in flags],
        note=note,
    )


# --- Report assembly --------------------------------------------------------


def build_quality_report(summary: BatchSummary) -> QualityReport:
    """Run :func:`analyze_paper` over every result in ``summary``."""
    papers: list[PaperQuality] = []
    flag_counts: dict[str, int] = {}
    for result in summary.results:
        pq = analyze_paper(result)
        if pq is None:
            continue
        papers.append(pq)
        for code in pq.flags:
            flag_counts[code] = flag_counts.get(code, 0) + 1

    flagged = sum(1 for p in papers if p.flags)
    return QualityReport(
        total=summary.total,
        flagged=flagged,
        failed=summary.failed,
        skipped=summary.skipped,
        flag_counts=dict(sorted(flag_counts.items(), key=lambda kv: -kv[1])),
        papers=papers,
    )


def format_report_markdown(report: QualityReport) -> str:
    """Render a human-readable report for inclusion in batch output dirs."""
    lines: list[str] = []
    lines.append("# Batch Quality Report")
    lines.append("")
    lines.append(f"- Total papers: **{report.total}**")
    lines.append(f"- Completed: **{report.total - report.failed - report.skipped}**")
    lines.append(f"- Failed: **{report.failed}**")
    lines.append(f"- Skipped (cached): **{report.skipped}**")
    lines.append(f"- Flagged for review: **{report.flagged}**")
    lines.append("")

    if report.flag_counts:
        lines.append("## Flag totals")
        lines.append("")
        for code, count in report.flag_counts.items():
            lines.append(f"- `{code}` — {count} paper(s)")
        lines.append("")

    flagged_papers = [p for p in report.papers if p.flags]
    if flagged_papers:
        lines.append("## Papers needing review")
        lines.append("")
        for p in flagged_papers:
            name = Path(p.path).name
            lines.append(f"### {name}")
            stats = (
                f"{p.pages}p · {p.sections} sec · {p.figures} fig · "
                f"{p.tables} tab · {p.references} ref · "
                f"conf {p.confidence:.2f} · {p.duration_s:.1f}s"
            )
            lines.append(f"_{stats}_")
            if p.note:
                lines.append(f"_{p.note}_")
            lines.append("")
            for code, msg in zip(p.flags, p.flag_messages):
                lines.append(f"- **{code}** — {msg}")
            lines.append("")

    clean_papers = [p for p in report.papers if not p.flags]
    if clean_papers:
        lines.append("## Clean papers")
        lines.append("")
        for p in clean_papers:
            name = Path(p.path).name
            lines.append(
                f"- {name} ({p.pages}p, {p.figures} fig, "
                f"{p.references} ref, conf {p.confidence:.2f})"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_quality_report(summary: BatchSummary, output_dir: Path | str) -> QualityReport:
    """Build the report and write ``report.md`` + ``report.json`` to disk."""
    out = Path(output_dir)
    report = build_quality_report(summary)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(format_report_markdown(report))
    (out / "report.json").write_text(report.model_dump_json(indent=2))
    return report


# --- Convenience API for callers --------------------------------------------


def papers_needing_review(report: QualityReport) -> Iterable[PaperQuality]:
    """Filter helper for downstream consumers (alerts, dashboards)."""
    return (p for p in report.papers if p.flags)
