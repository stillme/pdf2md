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
]


@dataclass
class BenchmarkResult:
    name: str
    category: str
    pages: int
    expected_pages: int
    title_extracted: bool
    title: str
    sections_found: int
    section_names: list[str]
    tables_found: int
    figures_found: int
    confidence: float
    time_ms: int
    error: str | None = None
    markdown_length: int = 0


def run_benchmarks(
    papers: list[dict] | None = None,
    tier: str = "fast",
    max_papers: int | None = None,
    skip_download_errors: bool = True,
) -> list[BenchmarkResult]:
    """Run pdf2md on benchmark papers and collect results."""
    import pdf2md

    if papers is None:
        papers = BENCHMARK_PAPERS

    if max_papers:
        papers = papers[:max_papers]

    results = []

    for paper in papers:
        name = paper["name"]
        url = paper["url"]
        print(f"\n{'='*60}")
        print(f"Benchmark: {name}")
        print(f"URL: {url}")

        # Download
        try:
            r = httpx.get(
                url,
                follow_redirects=True,
                timeout=60,
                headers={"User-Agent": "pdf2md-benchmark/1.0"},
            )
            if r.status_code != 200 or r.content[:5] != b"%PDF-":
                if skip_download_errors:
                    print(f"  SKIP: Download failed (status={r.status_code})")
                    results.append(BenchmarkResult(
                        name=name, category=paper.get("category", ""), pages=0,
                        expected_pages=paper.get("expected_pages", 0),
                        title_extracted=False, title="", sections_found=0,
                        section_names=[], tables_found=0, figures_found=0,
                        confidence=0, time_ms=0, error=f"Download failed: {r.status_code}",
                    ))
                    continue
                raise ValueError(f"Download failed: {r.status_code}")
            pdf_bytes = r.content
            print(f"  Downloaded: {len(pdf_bytes):,} bytes")
        except Exception as e:
            if skip_download_errors:
                print(f"  SKIP: {e}")
                results.append(BenchmarkResult(
                    name=name, category=paper.get("category", ""), pages=0,
                    expected_pages=paper.get("expected_pages", 0),
                    title_extracted=False, title="", sections_found=0,
                    section_names=[], tables_found=0, figures_found=0,
                    confidence=0, time_ms=0, error=str(e),
                ))
                continue
            raise

        # Convert
        try:
            doc = pdf2md.convert(pdf_bytes, tier=tier)

            result = BenchmarkResult(
                name=name,
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
            )
            results.append(result)

            print(f"  Pages: {result.pages} (expected {result.expected_pages})")
            print(f"  Title: {result.title[:60]}{'...' if len(result.title) > 60 else ''}")
            print(f"  Sections: {result.sections_found} — {result.section_names[:5]}")
            print(f"  Tables: {result.tables_found}")
            print(f"  Confidence: {result.confidence:.0%}")
            print(f"  Time: {result.time_ms}ms ({result.time_ms / max(result.pages, 1):.0f}ms/page)")
            print(f"  Markdown: {result.markdown_length:,} chars")

        except Exception as e:
            print(f"  ERROR: {e}")
            results.append(BenchmarkResult(
                name=name, category=paper.get("category", ""), pages=0,
                expected_pages=paper.get("expected_pages", 0),
                title_extracted=False, title="", sections_found=0,
                section_names=[], tables_found=0, figures_found=0,
                confidence=0, time_ms=0, error=str(e),
            ))

    return results


def print_summary(results: list[BenchmarkResult]) -> None:
    """Print a summary table of benchmark results."""
    print(f"\n{'='*80}")
    print("BENCHMARK SUMMARY")
    print(f"{'='*80}")
    print(f"{'Paper':<30} {'Pages':>5} {'Sects':>5} {'Tbls':>5} {'Conf':>6} {'Time':>8} {'Title':>5}")
    print("-" * 80)

    total_pages = 0
    total_time = 0
    successes = 0

    for r in results:
        if r.error:
            print(f"{r.name:<30} {'ERROR':>5}   {r.error[:40]}")
            continue

        successes += 1
        total_pages += r.pages
        total_time += r.time_ms
        title_ok = "Y" if r.title_extracted else "N"
        print(
            f"{r.name:<30} {r.pages:>5} {r.sections_found:>5} "
            f"{r.tables_found:>5} {r.confidence:>5.0%} {r.time_ms:>7}ms {title_ok:>5}"
        )

    print("-" * 80)
    if successes > 0:
        print(f"{'TOTAL':<30} {total_pages:>5} {'':>5} {'':>5} {'':>6} {total_time:>7}ms")
        print(
            f"{'AVG/PAGE':<30} {'':>5} {'':>5} {'':>5} "
            f"{'':>6} {total_time/max(total_pages,1):>6.0f}ms"
        )
    print(f"\n{successes}/{len(results)} papers processed successfully")
