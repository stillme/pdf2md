"""Benchmark runner — evaluate pdf2md on real papers."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import httpx


# Real open-access papers for benchmarking (arXiv, all CC-licensed)
BENCHMARK_PAPERS = [
    {
        "name": "mistral-7b",
        "url": "https://arxiv.org/pdf/2310.06825",
        "expected_pages": 9,
        "has_tables": True,
        "has_math": False,
        "category": "ml-paper",
    },
    {
        "name": "attention-is-all-you-need",
        "url": "https://arxiv.org/pdf/1706.03762",
        "expected_pages": 15,
        "has_tables": True,
        "has_math": True,
        "category": "ml-paper",
    },
    {
        "name": "gpt4-technical-report",
        "url": "https://arxiv.org/pdf/2303.08774",
        "expected_pages": 100,  # very long
        "has_tables": True,
        "has_math": False,
        "category": "technical-report",
    },
    {
        "name": "bert",
        "url": "https://arxiv.org/pdf/1810.04805",
        "expected_pages": 16,
        "has_tables": True,
        "has_math": False,
        "category": "ml-paper",
    },
    {
        "name": "nature-gut-adaptation",
        "path": "/Users/tmayassi/Downloads/s41586-024-08216-z.pdf",
        "url": "",
        "expected_pages": 41,
        "has_tables": True,
        "has_math": False,
        "category": "nature-article",
    },
    {
        "name": "dg-emi-model-math",
        "path": "/Users/tmayassi/Downloads/2411.02646v1.pdf",
        "url": "https://arxiv.org/pdf/2411.02646v1",
        "expected_pages": 30,
        "has_tables": True,
        "has_math": True,
        "category": "math-paper",
    },
]


@dataclass
class BenchmarkResult:
    name: str
    tier: str = "fast"
    category: str = ""
    pages: int = 0
    expected_pages: int = 0
    title_extracted: bool = False
    title: str = ""
    sections_found: int = 0
    section_names: list[str] = field(default_factory=list)
    tables_found: int = 0
    figures_found: int = 0
    confidence: float = 0.0
    time_ms: int = 0
    error: str | None = None
    markdown_length: int = 0
    equations_found: int = 0
    display_math_count: int = 0
    inline_math_count: int = 0


def _load_pdf(paper: dict, skip_errors: bool = True) -> bytes | None:
    """Load PDF bytes from local path or URL."""
    source = paper.get("path") or paper.get("url", "")
    name = paper["name"]

    if source.startswith("/") or source.startswith("~"):
        from pathlib import Path
        p = Path(source).expanduser()
        if not p.exists():
            if skip_errors:
                print(f"  SKIP: Local file not found: {p}")
                return None
            raise FileNotFoundError(f"Local file not found: {p}")
        pdf_bytes = p.read_bytes()
        print(f"  Loaded: {len(pdf_bytes):,} bytes (local)")
        return pdf_bytes
    else:
        r = httpx.get(
            source, follow_redirects=True, timeout=60,
            headers={"User-Agent": "pdf2md-benchmark/1.0"},
        )
        if r.status_code != 200 or r.content[:5] != b"%PDF-":
            if skip_errors:
                print(f"  SKIP: Download failed (status={r.status_code})")
                return None
            raise ValueError(f"Download failed: {r.status_code}")
        pdf_bytes = r.content
        print(f"  Downloaded: {len(pdf_bytes):,} bytes")
        return pdf_bytes


def _convert_paper(
    name: str, pdf_bytes: bytes, paper: dict, tier: str, provider: str | None = None,
    output_dir: str | None = None,
) -> BenchmarkResult:
    """Convert a single paper and return the result. Optionally save outputs."""
    import pdf2md
    from pathlib import Path

    kwargs = {"tier": tier}
    if provider:
        kwargs["provider"] = provider
    if tier in ("standard", "deep"):
        kwargs["figures"] = "describe"

    doc = pdf2md.convert(pdf_bytes, **kwargs)

    # Save outputs if output_dir specified
    if output_dir:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        suffix = f"-{tier}" if tier != "fast" else ""
        doc.save_markdown(str(out / f"{name}{suffix}.md"))
        doc.save_json(str(out / f"{name}{suffix}.json"))
        # Save figures to subdirectory
        fig_dir = out / f"{name}{suffix}-figures"
        if doc.figures and any(f.image_base64 for f in doc.figures):
            doc.save_figures(str(fig_dir))
        print(f"  Saved: {out / name}{suffix}.md, .json" + (f", {len(doc.figures)} figures" if doc.figures else ""))

    # Count math in markdown
    display_count = doc.markdown.count("$$") // 2  # pairs of $$
    inline_count = doc.markdown.count("$") - (display_count * 4)  # subtract $$ pairs
    inline_count = max(inline_count // 2, 0)  # pairs of $

    return BenchmarkResult(
        name=name,
        tier=tier,
        category=paper.get("category", ""),
        pages=doc.metadata.pages,
        expected_pages=paper.get("expected_pages", 0),
        title_extracted=doc.metadata.title is not None and len(doc.metadata.title) > 5,
        title=doc.metadata.title or "",
        sections_found=len(doc.sections),
        section_names=[s.title for s in doc.sections[:10]],
        tables_found=len(doc.tables),
        figures_found=len(doc.figures),
        confidence=doc.confidence,
        time_ms=doc.processing_time_ms,
        markdown_length=len(doc.markdown),
        equations_found=len(doc.equations),
        display_math_count=display_count,
        inline_math_count=inline_count,
    )


def run_benchmarks(
    papers: list[dict] | None = None,
    tier: str = "fast",
    max_papers: int | None = None,
    skip_download_errors: bool = True,
    provider: str | None = None,
    output_dir: str | None = None,
) -> list[BenchmarkResult]:
    """Run pdf2md on benchmark papers and collect results."""
    if papers is None:
        papers = BENCHMARK_PAPERS

    if max_papers:
        papers = papers[:max_papers]

    results = []

    for paper in papers:
        name = paper["name"]
        source = paper.get("path") or paper.get("url", "")
        print(f"\n{'='*60}")
        print(f"Benchmark: {name}")
        print(f"Source: {source[:80]}")

        try:
            pdf_bytes = _load_pdf(paper, skip_errors=skip_download_errors)
        except Exception as e:
            if skip_download_errors:
                print(f"  SKIP: {e}")
            results.append(_error_result(name, paper, str(e), tier))
            continue

        if pdf_bytes is None:
            results.append(_error_result(name, paper, "Failed to load", tier))
            continue

        try:
            result = _convert_paper(name, pdf_bytes, paper, tier, provider, output_dir)
            results.append(result)
            _print_result(result)
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append(_error_result(name, paper, str(e), tier))

    return results


def run_tier_comparison(
    papers: list[dict] | None = None,
    tiers: list[str] | None = None,
    max_papers: int | None = None,
    provider: str | None = None,
    output_dir: str | None = None,
) -> list[BenchmarkResult]:
    """Run each paper through multiple tiers and compare results side by side."""
    if papers is None:
        papers = BENCHMARK_PAPERS

    if max_papers:
        papers = papers[:max_papers]

    if tiers is None:
        tiers = ["fast", "standard", "deep"]

    results = []

    for paper in papers:
        name = paper["name"]
        source = paper.get("path") or paper.get("url", "")
        print(f"\n{'='*60}")
        print(f"Paper: {name}")
        print(f"Source: {source[:80]}")

        try:
            pdf_bytes = _load_pdf(paper)
        except Exception as e:
            print(f"  SKIP: {e}")
            continue

        if pdf_bytes is None:
            continue

        for tier in tiers:
            print(f"\n  --- {tier.upper()} tier ---")
            try:
                result = _convert_paper(f"{name}", pdf_bytes, paper, tier, provider, output_dir)
                result.tier = tier  # tag with tier for comparison
                results.append(result)
                _print_result(result, indent=4)
            except Exception as e:
                print(f"    ERROR: {e}")
                results.append(_error_result(name, paper, str(e), tier))

    return results


def _error_result(name: str, paper: dict, error: str, tier: str = "fast") -> BenchmarkResult:
    return BenchmarkResult(
        name=name, tier=tier, category=paper.get("category", ""), pages=0,
        expected_pages=paper.get("expected_pages", 0),
        title_extracted=False, title="", sections_found=0,
        section_names=[], tables_found=0, figures_found=0,
        confidence=0, time_ms=0, error=error,
    )


def _print_result(result: BenchmarkResult, indent: int = 2) -> None:
    pad = " " * indent
    print(f"{pad}Pages: {result.pages} (expected {result.expected_pages})")
    print(f"{pad}Title: {result.title[:60]}{'...' if len(result.title) > 60 else ''}")
    print(f"{pad}Sections: {result.sections_found} — {result.section_names[:5]}")
    print(f"{pad}Tables: {result.tables_found}")
    if result.display_math_count or result.inline_math_count:
        print(f"{pad}Math: {result.display_math_count} display + {result.inline_math_count} inline equations")
    print(f"{pad}Confidence: {result.confidence:.0%}")
    print(f"{pad}Time: {result.time_ms}ms ({result.time_ms / max(result.pages, 1):.0f}ms/page)")
    print(f"{pad}Markdown: {result.markdown_length:,} chars")


def print_summary(results: list[BenchmarkResult]) -> None:
    """Print a summary table of benchmark results."""
    # Check if this is a tier comparison (multiple tiers per paper)
    tiers_used = {r.tier for r in results if not r.error}
    is_comparison = len(tiers_used) > 1

    print(f"\n{'='*90}")
    print("BENCHMARK SUMMARY")
    print(f"{'='*90}")

    if is_comparison:
        print(f"{'Paper':<28} {'Tier':<9} {'Pages':>5} {'Sects':>5} {'Tbls':>5} {'Conf':>6} {'Time':>8} {'Chars':>8}")
        print("-" * 90)

        current_paper = None
        for r in results:
            if r.error:
                print(f"{r.name:<28} {r.tier:<9} {'ERROR':>5}   {r.error[:35]}")
                continue

            # Print paper name only on first tier
            paper_col = r.name if r.name != current_paper else ""
            current_paper = r.name
            print(
                f"{paper_col:<28} {r.tier:<9} {r.pages:>5} {r.sections_found:>5} "
                f"{r.tables_found:>5} {r.confidence:>5.0%} {r.time_ms:>7}ms {r.markdown_length:>7}"
            )
    else:
        print(f"{'Paper':<30} {'Pages':>5} {'Sects':>5} {'Tbls':>5} {'Conf':>6} {'Time':>8} {'Title':>5}")
        print("-" * 90)

        for r in results:
            if r.error:
                print(f"{r.name:<30} {'ERROR':>5}   {r.error[:40]}")
                continue

            title_ok = "Y" if r.title_extracted else "N"
            print(
                f"{r.name:<30} {r.pages:>5} {r.sections_found:>5} "
                f"{r.tables_found:>5} {r.confidence:>5.0%} {r.time_ms:>7}ms {title_ok:>5}"
            )

    print("-" * 90)
    successes = [r for r in results if not r.error]
    total_time = sum(r.time_ms for r in successes)
    total_pages = sum(r.pages for r in successes)
    if successes:
        print(f"{'TOTAL':<30} {total_pages:>5} {'':>5} {'':>5} {'':>6} {total_time:>7}ms")
    print(f"\n{len(successes)}/{len(results)} runs completed successfully")
