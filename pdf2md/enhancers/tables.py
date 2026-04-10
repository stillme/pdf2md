"""Table enhancer — uses VLM to correct low-confidence table extractions."""

from __future__ import annotations

import re

from pdf2md.document import Table
from pdf2md.providers.base import VLMProvider

# Tables above this confidence are not re-processed
CONFIDENCE_THRESHOLD = 0.7

_TABLE_CORRECTION_PROMPT = """\
The following markdown table was extracted from a PDF but may have errors (misaligned columns, missing cells, merged headers, OCR artifacts).

Current extraction:
{table_markdown}

Look at the page image and output ONLY the corrected markdown table. Fix any:
- Misaligned or missing columns
- Merged or split cells
- OCR errors in numbers or text
- Missing header or separator rows

Output ONLY the corrected markdown table, nothing else."""


def _parse_corrected_table(markdown: str) -> tuple[list[str], list[list[str]]]:
    """Parse headers and rows from corrected markdown table."""
    lines = [line.strip() for line in markdown.strip().splitlines() if line.strip()]

    headers: list[str] = []
    rows: list[list[str]] = []

    for i, line in enumerate(lines):
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        # Skip separator rows (all dashes/colons)
        if all(re.match(r"^[\s\-:]+$", cell) for cell in cells):
            continue
        if not headers:
            headers = cells
        else:
            rows.append(cells)

    return headers, rows


def enhance_table(
    table: Table,
    *,
    provider: VLMProvider | None,
    page_image: bytes | None = None,
) -> Table:
    """Enhance a table using VLM if confidence is below threshold.

    Args:
        table: The Table object to potentially enhance.
        provider: VLM provider for correction.
        page_image: PNG bytes of the page containing the table.

    Returns:
        The original or corrected Table object.
    """
    # High confidence tables are returned unchanged
    if table.confidence >= CONFIDENCE_THRESHOLD:
        return table

    # Without a provider or page image, return unchanged
    if provider is None or page_image is None:
        return table

    # Build the correction prompt
    prompt = _TABLE_CORRECTION_PROMPT.format(table_markdown=table.markdown)

    # Send to VLM with page image
    corrected_markdown = provider.complete_sync(prompt, image=page_image)

    # Parse the corrected table
    headers, rows = _parse_corrected_table(corrected_markdown)

    # Use the corrected version, boost confidence (capped at 0.9)
    new_confidence = min(table.confidence + 0.3, 0.9)

    return table.model_copy(update={
        "markdown": corrected_markdown.strip(),
        "headers": headers if headers else table.headers,
        "rows": rows if rows else table.rows,
        "confidence": new_confidence,
    })
