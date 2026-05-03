"""CLI — Click-based command-line interface for pdfvault."""

from __future__ import annotations

import json
import sys

import click

from pdfvault import __version__


@click.group()
@click.version_option(version=__version__, prog_name="pdfvault")
def main():
    """pdfvault — The first open-source agentic PDF-to-markdown parser."""


@main.command()
@click.argument("source")
@click.option("-o", "--output", default=None, help="Output file path (default: stdout).")
@click.option(
    "--tier",
    type=click.Choice(["auto", "fast", "standard", "deep"], case_sensitive=False),
    default="auto",
    help="Processing tier.",
)
@click.option(
    "--figures",
    type=click.Choice(["skip", "caption", "describe", "extract"], case_sensitive=False),
    default=None,
    help="Figure handling mode.",
)
@click.option("--provider", default=None, help="VLM provider override.")
@click.option("--verify/--no-verify", default=True, help="Run verification passes.")
@click.option(
    "--equations/--no-equations",
    default=True,
    help="VLM equation extraction on math-heavy pages. Disable for "
         "biomedical / text-heavy batch jobs to save VLM calls.",
)
@click.option("--json-output", "--json", "json_out", is_flag=True, help="Output as JSON.")
@click.option("--figures-json", default=None, help="Write lightweight figure index sidecar JSON.")
def convert(source, output, tier, figures, provider, verify, equations, json_out, figures_json):
    """Convert a PDF to markdown.

    SOURCE can be a file path or URL.
    """
    from pdfvault.core import convert as do_convert

    try:
        doc = do_convert(
            source,
            tier=tier,
            figures=figures,
            verify=verify,
            provider=provider,
            equations=equations,
        )
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if json_out:
        content = doc.model_dump_json(indent=2)
    else:
        content = doc.markdown

    if output:
        with open(output, "w") as f:
            f.write(content)
        click.echo(f"Written to {output}")
    else:
        click.echo(content)

    if figures_json:
        doc.save_figure_index(figures_json)
        click.echo(f"Figure index written to {figures_json}", err=True)


@main.command()
@click.option("--tier", default="fast", type=click.Choice(["fast", "standard", "deep"]))
@click.option("--max-papers", default=None, type=int, help="Limit number of papers")
@click.option("--compare", is_flag=True, help="Compare all tiers side by side")
@click.option("--provider", default=None, help="VLM provider for standard/deep tiers")
@click.option("-o", "--output-dir", default=None, help="Save markdown, JSON, and figures per paper")
def benchmark(tier, max_papers, compare, provider, output_dir):
    """Run benchmarks on real open-access papers.

    Use --compare to run each paper through fast, standard, and deep tiers.
    Use -o/--output-dir to save full outputs (markdown, JSON, figures) per paper.
    """
    from pdfvault.benchmarks.runner import run_benchmarks, run_tier_comparison, print_summary

    if compare:
        click.echo("Running pdfvault tier comparison benchmark...")
        results = run_tier_comparison(max_papers=max_papers, provider=provider, output_dir=output_dir)
    else:
        click.echo(f"Running pdfvault benchmarks (tier={tier})...")
        results = run_benchmarks(tier=tier, max_papers=max_papers, provider=provider, output_dir=output_dir)
    print_summary(results)
    if output_dir:
        click.echo(f"\nOutputs saved to: {output_dir}/")


@main.command()
@click.argument("input_path")
@click.option(
    "-o", "--output-dir",
    required=True,
    help="Directory where per-paper .md and .json outputs are written.",
)
@click.option(
    "--tier",
    type=click.Choice(["fast", "standard", "deep"], case_sensitive=False),
    default="standard",
    help="Processing tier (default: standard).",
)
@click.option("--provider", default=None, help="VLM provider override.")
@click.option(
    "--figures",
    type=click.Choice(["skip", "caption", "describe", "extract"], case_sensitive=False),
    default="describe",
    help="Figure handling mode (default: describe).",
)
@click.option(
    "--equations/--no-equations",
    default=True,
    help="VLM equation extraction. Disable for biomedical / text-heavy batches.",
)
@click.option("--verify/--no-verify", default=True, help="Run verification passes.")
@click.option(
    "--concurrency",
    type=int,
    default=1,
    help="Parallel workers. Default 1; raise only with high-quota providers.",
)
@click.option(
    "--checkpoint",
    default=None,
    help="Checkpoint JSON path (default: <output-dir>/.pdfvault-batch.json).",
)
@click.option(
    "--resume/--no-resume",
    default=True,
    help="Skip papers already marked completed in the checkpoint.",
)
@click.option(
    "--max-papers",
    type=int,
    default=None,
    help="Limit to the first N papers (after sorted discovery).",
)
def batch(
    input_path,
    output_dir,
    tier,
    provider,
    figures,
    equations,
    verify,
    concurrency,
    checkpoint,
    resume,
    max_papers,
):
    """Convert a directory or glob of PDFs to markdown.

    INPUT_PATH may be a directory (recursively scanned for *.pdf) or a glob
    pattern. Per-paper failures are isolated and recorded in the checkpoint
    so the batch keeps running. Re-running on the same output directory
    resumes from the last checkpoint.
    """
    from pathlib import Path
    from pdfvault.batch import (
        discover_pdfs,
        format_summary_table,
        run_batch,
        stderr_progress_printer,
    )

    try:
        inputs = discover_pdfs(input_path)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if not inputs:
        click.echo(f"No PDFs found at {input_path}", err=True)
        sys.exit(1)

    if max_papers is not None:
        inputs = inputs[:max_papers]

    out_dir = Path(output_dir)
    checkpoint_path = Path(checkpoint) if checkpoint else None

    click.echo(
        f"Processing {len(inputs)} PDFs -> {out_dir} "
        f"(tier={tier}, concurrency={concurrency}, resume={resume})",
        err=True,
    )

    summary = run_batch(
        inputs=inputs,
        output_dir=out_dir,
        tier=tier,
        provider=provider,
        figures=figures,
        equations=equations,
        verify=verify,
        concurrency=concurrency,
        checkpoint_path=checkpoint_path,
        resume=resume,
        on_progress=stderr_progress_printer(),
    )

    # Quality report — write report.md / report.json next to outputs.
    # At corpus scale users can't read every output; the report turns
    # 1000 markdown files into a one-page anomaly inbox.
    from pdfvault.quality_report import write_quality_report
    report = write_quality_report(summary, out_dir)

    click.echo(format_summary_table(summary, flagged=report.flagged))

    # Exit non-zero only if every paper failed. A partial batch is still
    # useful — the user wants to know what we got, not be blocked by one
    # bad PDF in a corpus of hundreds.
    if summary.completed == 0 and summary.failed > 0:
        sys.exit(2)


@main.command()
def info():
    """Show available engines and providers."""
    from pdfvault.extractors import get_available_extractors

    click.echo("pdfvault engine status:")
    click.echo()

    # Core engines (always available)
    available = get_available_extractors()
    available_names = {ext.name for ext in available}

    all_engines = [
        ("pypdfium2", "Core text + image extraction"),
        ("pdfplumber", "Table extraction specialist"),
        ("marker", "ML-based document understanding"),
        ("pymupdf", "Fast text + rendering"),
        ("docling", "IBM document AI"),
    ]

    for name, desc in all_engines:
        status = "installed" if name in available_names else "not installed"
        mark = "+" if name in available_names else "-"
        click.echo(f"  [{mark}] {name:14s} {desc:40s} ({status})")

    click.echo()

    # Check for VLM provider API keys
    import os
    providers = [
        ("OpenAI", "OPENAI_API_KEY"),
        ("Anthropic", "ANTHROPIC_API_KEY"),
        ("Google", "GOOGLE_API_KEY"),
    ]

    click.echo("VLM providers:")
    for name, env_var in providers:
        has_key = bool(os.environ.get(env_var))
        mark = "+" if has_key else "-"
        status = "API key set" if has_key else "no API key"
        click.echo(f"  [{mark}] {name:14s} ({status})")
