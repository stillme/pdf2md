"""Core orchestrator — convert() drives triage, extraction, assembly."""

from __future__ import annotations

import time
from io import BytesIO
from pathlib import Path
from typing import Sequence

import pypdfium2 as pdfium

from pdf2md.assembler import assemble_markdown
from pdf2md.config import Config, FigureMode, Tier
from pdf2md.document import Document
from pdf2md.enhancers.captions import extract_figure_captions, extract_panel_references, match_captions_to_figures
from pdf2md.enhancers.figures import enhance_figures
from pdf2md.enhancers.math import convert_unicode_math, detect_math_regions, extract_equations_vlm
from pdf2md.enhancers.metadata import extract_metadata
from pdf2md.enhancers.tables import enhance_table
from pdf2md.enhancers.text_cleaner import clean_figure_text
from pdf2md.extractors import get_available_extractors, get_extractor_by_name
from pdf2md.extractors.base import PageContent, RawFigure
from pdf2md.providers.base import VLMProvider
from pdf2md.providers.registry import get_provider
from pdf2md.triage.analyzer import analyze_page
from pdf2md.triage.router import select_engine, select_tier
from pdf2md.verifier import run_verify_loop


def _resolve_source(source: str | bytes) -> bytes:
    """Resolve a file path, URL, or raw bytes to PDF bytes."""
    if isinstance(source, bytes):
        return source

    if isinstance(source, str):
        # Check if it looks like a URL
        if source.startswith(("http://", "https://")):
            import httpx
            resp = httpx.get(source, follow_redirects=True, timeout=60)
            resp.raise_for_status()
            return resp.content

        # Treat as file path
        p = Path(source)
        if not p.exists():
            raise FileNotFoundError(f"PDF file not found: {source}")
        return p.read_bytes()

    raise TypeError(f"Unsupported source type: {type(source)}")


def _count_pages(pdf_bytes: bytes) -> int:
    """Count pages using pypdfium2. Raises ValueError for invalid PDFs."""
    try:
        pdf = pdfium.PdfDocument(pdf_bytes)
    except Exception as e:
        raise ValueError(f"Invalid PDF: {e}") from e
    n = len(pdf)
    pdf.close()
    return n


def _merge_tables(primary: PageContent, table_source: PageContent) -> PageContent:
    """Merge tables from table_source into primary page content."""
    if table_source.tables and not primary.tables:
        primary = primary.model_copy(update={"tables": table_source.tables})
    return primary


def _get_vlm_provider(provider_string: str | None = None) -> VLMProvider | None:
    """Get a VLM provider, returning None if unavailable."""
    try:
        return get_provider(provider_string)
    except Exception:
        return None


def _render_page_image(pdf_bytes: bytes, page_number: int, dpi: int = 150) -> bytes | None:
    """Render a PDF page to PNG bytes for VLM enhancement."""
    try:
        pdf = pdfium.PdfDocument(pdf_bytes)
        if page_number < 0 or page_number >= len(pdf):
            pdf.close()
            return None
        page = pdf[page_number]
        scale = dpi / 72
        bitmap = page.render(scale=scale)
        pil_image = bitmap.to_pil()
        page.close()
        pdf.close()

        buf = BytesIO()
        pil_image.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None


def convert(
    source: str | bytes,
    *,
    tier: str | Tier = Tier.AUTO,
    figures: str | None = None,
    verify: bool = True,
    provider: str | None = None,
) -> Document:
    """Convert a PDF to a structured markdown Document.

    Args:
        source: File path, URL, or raw PDF bytes.
        tier: Processing tier — "fast", "standard", "deep", or "auto".
        figures: Figure handling mode (skip, caption, describe, extract).
        verify: Whether to run verification passes.
        provider: VLM provider override.

    Returns:
        A Document with markdown, sections, tables, figures, and metadata.
    """
    t0 = time.monotonic()

    # Resolve input to bytes
    pdf_bytes = _resolve_source(source)

    # Validate and count pages
    num_pages = _count_pages(pdf_bytes)

    # Resolve tier enum
    if isinstance(tier, str):
        tier = Tier(tier)

    # Build config
    config = Config(
        tier=tier,
        verify=verify,
        provider=provider,
    )
    if figures is not None:
        config = config.model_copy(update={"figures": figures})

    # Discover available engines
    available = get_available_extractors()
    available_names = [ext.name for ext in available]

    # Process each page: triage -> select tier/engines -> extract
    all_pages: list[PageContent] = []

    for page_idx in range(num_pages):
        # Triage: analyze page complexity
        analysis = analyze_page(pdf_bytes, page_idx)

        # Select tier and engines for this page
        page_tier = select_tier(analysis, config.tier)
        engines = select_engine(
            page_tier,
            has_text_layer=analysis.has_text_layer,
            available_engines=available_names,
            has_tables=analysis.has_tables,
        )

        # Extract with primary engine
        primary_engine_name = engines[0] if engines else "pypdfium2"
        primary_ext = get_extractor_by_name(primary_engine_name)
        if primary_ext is None:
            # Fallback
            primary_ext = get_extractor_by_name("pypdfium2")

        page_content = primary_ext.extract_page(pdf_bytes, page_idx)

        # If pdfplumber is a secondary engine, merge its tables
        if (
            len(engines) > 1
            and "pdfplumber" in engines
            and primary_engine_name != "pdfplumber"
        ):
            plumber_ext = get_extractor_by_name("pdfplumber")
            if plumber_ext is not None:
                plumber_page = plumber_ext.extract_page(pdf_bytes, page_idx)
                page_content = _merge_tables(page_content, plumber_page)

        all_pages.append(page_content)

    # Extract bold headings and enhanced figures if PyMuPDF is available
    bold_headings: list[dict] | None = None
    try:
        from pdf2md.extractors.pymupdf_ext import PymupdfExtractor
        pymupdf_ext = PymupdfExtractor()

        # Bold heading detection for journals like Nature
        bold_headings = pymupdf_ext.extract_bold_headings(pdf_bytes)

        # Enhanced figure extraction with size filtering
        pymupdf_figures = pymupdf_ext.extract_figures(pdf_bytes)
        if pymupdf_figures:
            # Build a dict of page_number -> list[RawFigure] from PyMuPDF's
            # high-quality large figures (200x200+). These replace whatever
            # the primary extractor found (which may be tiny/spurious).
            pymupdf_by_page: dict[int, list[RawFigure]] = {}
            for fig_info in pymupdf_figures:
                fig_page = fig_info["page"]
                if fig_page < len(all_pages):
                    pymupdf_by_page.setdefault(fig_page, []).append(
                        RawFigure(
                            image_bytes=fig_info["image_bytes"],
                            caption=None,
                            bbox=None,
                        )
                    )
            for page_num, figs in pymupdf_by_page.items():
                all_pages[page_num] = all_pages[page_num].model_copy(
                    update={"figures": figs}
                )
    except ImportError:
        pass

    # Assemble into Document
    doc = assemble_markdown(all_pages, bold_headings=bold_headings)

    # Enhance metadata: extract title, authors, DOI from assembled text
    full_text = "\n".join(p.text for p in all_pages)
    extracted_meta = extract_metadata(full_text, pages=num_pages)
    updated_meta = doc.metadata.model_copy(update={
        "title": extracted_meta.title or doc.metadata.title,
        "authors": extracted_meta.authors or doc.metadata.authors,
        "doi": extracted_meta.doi or doc.metadata.doi,
    })
    doc = doc.model_copy(update={"metadata": updated_meta})

    # Clean figure-leak text (axis labels, gene names from figures)
    doc = doc.model_copy(update={
        "markdown": clean_figure_text(doc.markdown),
    })

    # Extract and match figure captions from the assembled markdown
    captions = extract_figure_captions(doc.markdown)
    if captions and doc.figures:
        doc = doc.model_copy(update={
            "figures": match_captions_to_figures(doc.figures, captions),
        })

    # Store panel references as metadata (available via doc internals)
    _panel_refs = extract_panel_references(doc.markdown)

    # Math enhancement (all tiers): convert Unicode math symbols to LaTeX
    doc = doc.model_copy(update={
        "markdown": convert_unicode_math(doc.markdown),
    })

    # VLM enhancement for STANDARD and DEEP tiers
    effective_tier_enum = config.tier
    if effective_tier_enum == Tier.AUTO and num_pages > 0:
        analysis0 = analyze_page(pdf_bytes, 0)
        effective_tier_enum = select_tier(analysis0, Tier.AUTO)

    if effective_tier_enum in (Tier.STANDARD, Tier.DEEP):
        vlm = _get_vlm_provider(config.provider)
        if vlm is not None:
            # Enhance figures if mode is DESCRIBE or EXTRACT
            if config.figures in (FigureMode.DESCRIBE, FigureMode.EXTRACT):
                doc = doc.model_copy(update={
                    "figures": enhance_figures(
                        doc.figures,
                        mode=config.figures,
                        provider=vlm,
                        output_dir=config.output_dir,
                    ),
                })

            # Enhance low-confidence tables
            enhanced_tables = []
            for table in doc.tables:
                page_image = _render_page_image(pdf_bytes, table.page)
                enhanced_tables.append(
                    enhance_table(table, provider=vlm, page_image=page_image)
                )
            if enhanced_tables:
                doc = doc.model_copy(update={"tables": enhanced_tables})

            # VLM equation extraction on math-heavy pages
            all_equations = list(doc.equations)
            for page_idx_eq in range(num_pages):
                page_text = all_pages[page_idx_eq].text
                if not detect_math_regions(page_text):
                    continue
                page_image = _render_page_image(pdf_bytes, page_idx_eq)
                if page_image is None:
                    continue
                eqs = extract_equations_vlm(
                    page_image=page_image,
                    page_text=page_text,
                    provider=vlm,
                    page_number=page_idx_eq,
                )
                all_equations.extend(eqs)
            if all_equations:
                doc = doc.model_copy(update={"equations": all_equations})

    # Agentic verify-correct loop for DEEP tier
    if effective_tier_enum == Tier.DEEP and config.verify:
        vlm_verify = _get_vlm_provider(config.provider)
        if vlm_verify is not None:
            corrected_pages = list(all_pages)
            for i, page in enumerate(corrected_pages):
                page_image = _render_page_image(pdf_bytes, page.page_number)
                if page_image is None:
                    continue
                corrected_md, confidence = run_verify_loop(
                    page_image,
                    page.text,
                    vlm_verify,
                    max_rounds=config.max_verify_rounds,
                )
                corrected_pages[i] = page.model_copy(update={
                    "text": corrected_md,
                    "confidence": max(page.confidence, confidence),
                })
            # Reassemble with corrected pages
            all_pages = corrected_pages
            doc = assemble_markdown(all_pages, bold_headings=bold_headings)

            # Re-extract metadata lost during reassembly
            full_text_corrected = "\n".join(p.text for p in all_pages)
            meta = extract_metadata(full_text_corrected, doc.metadata.pages)
            updated_meta = doc.metadata.model_copy(update={
                "title": meta.title or doc.metadata.title,
                "authors": meta.authors or doc.metadata.authors,
                "doi": meta.doi or doc.metadata.doi,
            })
            doc = doc.model_copy(update={"metadata": updated_meta})

    # Stamp tier and timing
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    effective_tier = tier.value if isinstance(tier, Tier) else str(tier)
    # For auto tier, report the tier that was actually used for page 0
    if config.tier == Tier.AUTO and num_pages > 0:
        analysis0 = analyze_page(pdf_bytes, 0)
        effective_tier = select_tier(analysis0, Tier.AUTO).value

    doc = doc.model_copy(update={
        "processing_time_ms": elapsed_ms,
        "tier_used": effective_tier,
        "engine_used": primary_engine_name,
    })

    return doc


def convert_batch(
    sources: Sequence[str | bytes],
    *,
    tier: str | Tier = Tier.AUTO,
    figures: str | None = None,
    verify: bool = True,
    provider: str | None = None,
) -> list[Document]:
    """Convert multiple PDFs sequentially.

    Args:
        sources: List of file paths, URLs, or raw PDF bytes.
        tier: Processing tier for all documents.
        figures: Figure handling mode.
        verify: Whether to run verification passes.
        provider: VLM provider override.

    Returns:
        List of Documents, one per source.
    """
    results: list[Document] = []
    for source in sources:
        doc = convert(
            source,
            tier=tier,
            figures=figures,
            verify=verify,
            provider=provider,
        )
        results.append(doc)
    return results
