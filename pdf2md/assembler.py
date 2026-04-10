"""Markdown assembler — constructs a Document from extracted page content."""

from __future__ import annotations

import re
from collections import Counter

from pdf2md.document import Document, Figure, Metadata, Section, Table
from pdf2md.extractors.base import PageContent

# Heading patterns: common scientific paper section names
_HEADING_PATTERNS = re.compile(
    r"^(?:Abstract|Introduction|Background|Methods|Materials and Methods|"
    r"Results|Discussion|Conclusions?|References|Acknowledgm?ents?|"
    r"Supplementary(?:\s+Materials?)?|Appendi(?:x|ces))$",
    re.IGNORECASE,
)

# ALL CAPS short lines (>3 chars, <=6 words) as headings
_ALLCAPS_RE = re.compile(r"^[A-Z][A-Z\s\-:&]{2,}$")

# Lone page number pattern
_PAGE_NUMBER_RE = re.compile(r"^\s*\d{1,4}\s*$")


def _is_heading(line: str) -> bool:
    """Determine if a line is a section heading."""
    stripped = line.strip()
    if not stripped or len(stripped) > 80:
        return False
    # Reject lines with mid-line period-space (likely a sentence, not a heading)
    if ". " in stripped and not stripped.endswith("."):
        return False
    if _HEADING_PATTERNS.match(stripped):
        return True
    # ALL CAPS: >3 chars, <=6 words
    if _ALLCAPS_RE.match(stripped) and len(stripped) > 3:
        words = stripped.split()
        if len(words) <= 6:
            return True
    return False


def _detect_repeated_lines(pages: list[PageContent]) -> set[str]:
    """Find lines appearing as first or last line on 50%+ of pages (headers/footers)."""
    if len(pages) < 2:
        return set()

    first_lines: list[str] = []
    last_lines: list[str] = []

    for page in pages:
        lines = page.text.strip().splitlines()
        if lines:
            first_lines.append(lines[0].strip())
            last_lines.append(lines[-1].strip())

    threshold = len(pages) * 0.5
    repeated = set()

    for line, count in Counter(first_lines).items():
        if count >= threshold and count >= 2 and line:
            repeated.add(line)
    for line, count in Counter(last_lines).items():
        if count >= threshold and count >= 2 and line:
            repeated.add(line)

    return repeated


def _clean_page_text(text: str, repeated_lines: set[str]) -> str:
    """Strip repeated headers/footers and lone page numbers."""
    lines = text.splitlines()
    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped in repeated_lines:
            continue
        if _PAGE_NUMBER_RE.match(stripped):
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


def assemble_markdown(pages: list[PageContent]) -> Document:
    """Assemble extracted page content into a structured Document."""
    repeated_lines = _detect_repeated_lines(pages)

    md_parts: list[str] = []
    sections: list[Section] = []
    all_tables: list[Table] = []
    all_figures: list[Figure] = []
    page_confidences: list[float] = []

    table_counter = 0
    figure_counter = 0

    for page in pages:
        page_confidences.append(page.confidence)
        text = _clean_page_text(page.text, repeated_lines)

        # Parse text into lines, detect headings, build markdown
        page_lines = text.splitlines()
        page_md_parts: list[str] = []
        current_heading: str | None = None
        current_content_lines: list[str] = []

        for line in page_lines:
            stripped = line.strip()
            if _is_heading(stripped):
                # Flush previous section
                if current_heading is not None:
                    content = "\n".join(current_content_lines).strip()
                    sections.append(Section(
                        level=1,
                        title=current_heading,
                        content=content,
                        page=page.page_number,
                    ))
                current_heading = stripped
                current_content_lines = []
                page_md_parts.append(f"\n## {stripped}\n")
            else:
                current_content_lines.append(line)
                if stripped:
                    page_md_parts.append(line)
                else:
                    page_md_parts.append("")

        # Flush the last heading's content
        if current_heading is not None:
            content = "\n".join(current_content_lines).strip()
            sections.append(Section(
                level=1,
                title=current_heading,
                content=content,
                page=page.page_number,
            ))

        # Add tables from this page
        for raw_table in page.tables:
            table_counter += 1
            table_id = f"tbl{table_counter}"
            all_tables.append(Table(
                id=table_id,
                markdown=raw_table.markdown,
                headers=raw_table.headers,
                rows=raw_table.rows,
                page=page.page_number,
                confidence=raw_table.confidence,
            ))
            page_md_parts.append(f"\n{raw_table.markdown}\n")

        # Add figures from this page
        for raw_fig in page.figures:
            figure_counter += 1
            fig_id = f"fig{figure_counter}"
            all_figures.append(Figure(
                id=fig_id,
                caption=raw_fig.caption,
                page=page.page_number,
            ))
            if raw_fig.caption:
                page_md_parts.append(f"\n![{raw_fig.caption}]({fig_id})\n")
            else:
                page_md_parts.append(f"\n![Figure {figure_counter}]({fig_id})\n")

        md_parts.append("\n".join(page_md_parts))

    # Join pages with double newline
    full_markdown = "\n\n".join(md_parts).strip()

    # Clean up excessive blank lines
    full_markdown = re.sub(r"\n{3,}", "\n\n", full_markdown)

    # Calculate average confidence
    avg_confidence = 0.0
    if page_confidences:
        avg_confidence = sum(page_confidences) / len(page_confidences)

    metadata = Metadata(pages=len(pages))

    return Document(
        markdown=full_markdown,
        metadata=metadata,
        sections=sections,
        figures=all_figures,
        tables=all_tables,
        confidence=avg_confidence,
        page_confidences=page_confidences,
    )
