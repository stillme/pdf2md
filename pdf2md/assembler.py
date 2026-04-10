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

# Numbered headings with known section names: "1 Introduction", "2.1 Methods", "1. Results"
_NUMBERED_KNOWN_RE = re.compile(
    r"^(\d+(?:\.\d+)*)\.?\s+"
    r"(Introduction|Background|Methods?|Materials and Methods|Results?"
    r"|Discussion|Conclusions?|Summary|References|Bibliography"
    r"|Acknowledgments?|Appendix|Abstract)$",
    re.IGNORECASE,
)

# General numbered headings: "2.1 Data Collection", "3. Weak formulation"
# Title must start uppercase, be 2-40 chars, and NOT be ALL CAPS (those are likely running headers)
_NUMBERED_GENERAL_RE = re.compile(
    r"^(\d+(?:\.\d+)*)\.?\s+([A-Z][a-z][a-zA-Z\s,\-]{1,40})$"
)

# ALL CAPS short lines (>3 chars, <=6 words) as headings
_ALLCAPS_RE = re.compile(r"^[A-Z][A-Z\s\-:&]{2,}$")

# Lone page number pattern
_PAGE_NUMBER_RE = re.compile(r"^\s*\d{1,4}\s*$")


def _numbering_depth(num_str: str) -> int:
    """Return heading level from numbering: '1' -> 1, '1.1' -> 2, '1.1.1' -> 3."""
    return num_str.count('.') + 1


def _is_heading(line: str) -> dict | None:
    """Determine if a line is a section heading.

    Returns a dict with 'text' and 'level' if the line is a heading, or None.
    """
    stripped = line.strip()
    if not stripped or len(stripped) > 80:
        return None

    # Check ALL numbered heading patterns BEFORE the period-space rejection,
    # since "1. Introduction" and "2. Problem statement" legitimately contain ". "
    m = _NUMBERED_KNOWN_RE.match(stripped)
    if m:
        return {"text": stripped, "level": _numbering_depth(m.group(1))}

    m = _NUMBERED_GENERAL_RE.match(stripped)
    if m:
        return {"text": stripped, "level": _numbering_depth(m.group(1))}

    # Reject lines with mid-line period-space (likely a sentence, not a heading)
    if ". " in stripped and not stripped.endswith("."):
        return None

    # Standard section names (unnumbered)
    if _HEADING_PATTERNS.match(stripped):
        return {"text": stripped, "level": 1}

    # ALL CAPS: require at least 2 words AND minimum 8 characters total
    if _ALLCAPS_RE.match(stripped) and len(stripped) >= 8:
        words = stripped.split()
        if len(words) >= 2 and len(words) <= 6:
            # Reject figure panel label patterns: all tokens are 1-3 letter uppercase
            # (e.g. "SPF GF FMT", "AB CD AB CD AB CD", "WT KO WT KO")
            if all(len(w) <= 3 for w in words):
                return None
            return {"text": stripped, "level": 1}

    return None


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


def _build_table_cell_set(raw_tables: list) -> set[str]:
    """Build a set of cell values from all tables on a page for dedup matching."""
    cells = set()
    for tbl in raw_tables:
        for h in tbl.headers:
            h_stripped = h.strip()
            if h_stripped and len(h_stripped) > 1:
                cells.add(h_stripped)
        for row in tbl.rows:
            for cell in row:
                c_stripped = cell.strip()
                if c_stripped and len(c_stripped) > 1:
                    cells.add(c_stripped)
    return cells


def _remove_table_text_from_lines(lines: list[str], table_cells: set[str]) -> list[str]:
    """Remove text lines that overlap heavily with table cell content.

    A line is considered table-duplicate if most of its whitespace-separated
    tokens appear in the table cell set.
    """
    if not table_cells:
        return lines

    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned.append(line)
            continue
        tokens = stripped.split()
        if len(tokens) < 2:
            cleaned.append(line)
            continue
        # Count how many tokens match a table cell value
        match_count = sum(1 for t in tokens if t in table_cells)
        # If more than half the tokens match table cells, it's likely table text
        if match_count / len(tokens) > 0.5:
            continue  # skip this line
        cleaned.append(line)
    return cleaned


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

        # Bug 3 fix: remove text lines that duplicate table content
        if page.tables:
            table_cells = _build_table_cell_set(page.tables)
            page_lines = _remove_table_text_from_lines(page_lines, table_cells)

        page_md_parts: list[str] = []
        current_heading: str | None = None
        current_heading_level: int = 1
        current_content_lines: list[str] = []

        for line in page_lines:
            stripped = line.strip()
            heading_info = _is_heading(stripped)
            if heading_info is not None:
                # Flush previous section
                if current_heading is not None:
                    content = "\n".join(current_content_lines).strip()
                    sections.append(Section(
                        level=current_heading_level,
                        title=current_heading,
                        content=content,
                        page=page.page_number,
                    ))
                current_heading = heading_info["text"]
                current_heading_level = heading_info["level"]
                current_content_lines = []
                # Map level to markdown heading: 1 -> ##, 2 -> ###, 3 -> ####
                md_level = "#" * (heading_info["level"] + 1)
                page_md_parts.append(f"\n{md_level} {heading_info['text']}\n")
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
                level=current_heading_level,
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

    # Deduplicate repeated section titles (running headers detected as headings).
    # Any title appearing on 3+ pages is treated as a running header, not a real section.
    title_counts = Counter(s.title for s in sections)
    seen_titles: set[str] = set()
    deduped_sections: list[Section] = []
    for s in sections:
        if title_counts[s.title] >= 3 and s.title in seen_titles:
            continue  # skip repeated running header
        seen_titles.add(s.title)
        deduped_sections.append(s)
    sections = deduped_sections

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
