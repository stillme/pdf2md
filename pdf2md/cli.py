"""CLI — Click-based command-line interface for pdf2md."""

from __future__ import annotations

import json
import sys

import click

from pdf2md import __version__


@click.group()
@click.version_option(version=__version__, prog_name="pdf2md")
def main():
    """pdf2md — The first open-source agentic PDF-to-markdown parser."""


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
@click.option("--json-output", "--json", "json_out", is_flag=True, help="Output as JSON.")
@click.option("--figures-json", default=None, help="Write lightweight figure index sidecar JSON.")
def convert(source, output, tier, figures, provider, verify, json_out, figures_json):
    """Convert a PDF to markdown.

    SOURCE can be a file path or URL.
    """
    from pdf2md.core import convert as do_convert

    try:
        doc = do_convert(
            source,
            tier=tier,
            figures=figures,
            verify=verify,
            provider=provider,
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
    from pdf2md.benchmarks.runner import run_benchmarks, run_tier_comparison, print_summary

    if compare:
        click.echo("Running pdf2md tier comparison benchmark...")
        results = run_tier_comparison(max_papers=max_papers, provider=provider, output_dir=output_dir)
    else:
        click.echo(f"Running pdf2md benchmarks (tier={tier})...")
        results = run_benchmarks(tier=tier, max_papers=max_papers, provider=provider, output_dir=output_dir)
    print_summary(results)
    if output_dir:
        click.echo(f"\nOutputs saved to: {output_dir}/")


@main.command()
def info():
    """Show available engines and providers."""
    from pdf2md.extractors import get_available_extractors

    click.echo("pdf2md engine status:")
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
