"""Metadata enhancer — extract title, authors, DOI from text using heuristics."""

from __future__ import annotations

import re

from pdf2md.document import Metadata

# Section headings that signal the end of the front-matter block
_SECTION_HEADINGS = re.compile(
    r"^\s*(abstract|introduction|background|methods?|results?|discussion|"
    r"conclusion|references?|acknowledgements?|keywords?)\s*$",
    re.IGNORECASE,
)

# DOI pattern — matches "DOI: 10.xxx/yyy" or bare "10.xxx/yyy"
_DOI_PATTERN = re.compile(
    r"(?:doi\s*:\s*)?(10\.\d{4,9}/[^\s\"'<>]+)",
    re.IGNORECASE,
)

# Author line heuristic: comma-separated chunks where each chunk looks like a name
# Each name segment: 1-5 words (allows "van der Berg", "Jr.", initials, etc.)
_NAME_SEGMENT = re.compile(
    r"^(?:[A-Z][a-zA-Z\-'\.]+\.?(?:\s+[A-Z][a-zA-Z\-'\.]+\.?){0,4})$"
)

# Words that indicate a line is license/copyright text — not a title
_LICENSE_WORDS = re.compile(
    r"\b(license|copyright|permission|granted|rights?\s+reserved|creative\s+commons)\b",
    re.IGNORECASE,
)

# Words that indicate an institutional affiliation line — not a title
_AFFILIATION_WORDS = re.compile(
    r"\b(university|department|dept\.?|institute|institution|hospital|school\s+of|"
    r"faculty|laboratory|lab\b|college|centre|center)\b",
    re.IGNORECASE,
)

# URL / DOI line detector
_URL_OR_DOI = re.compile(
    r"(https?://|www\.|10\.\d{4,9}/|doi\.org)",
    re.IGNORECASE,
)


def _looks_like_name(token: str) -> bool:
    """Return True if `token` looks like a person's name."""
    token = token.strip()
    if not token:
        return False
    # Replace " and " connectors so "Alice and Bob" → ["Alice", "Bob"]
    # (handled in caller; here we check a single name)
    words = token.split()
    if not (1 <= len(words) <= 5):
        return False
    # Each word should start with an uppercase letter or be an initial (single char + period)
    for w in words:
        if not w:
            continue
        if not (w[0].isupper() or re.match(r"^[A-Z]\.$", w)):
            return False
    return True


def _is_author_line(stripped: str) -> bool:
    """Return True if the line looks like a list of author names."""
    normalised = re.sub(r"\s+and\s+", ", ", stripped, flags=re.IGNORECASE)
    parts = [p.strip() for p in normalised.split(",") if p.strip()]
    return len(parts) >= 2 and all(_looks_like_name(p) for p in parts)


def _should_skip_as_title(stripped: str) -> bool:
    """Return True if this line should be skipped when searching for the title."""
    if not stripped:
        return True
    # Too short or too long
    if not (5 <= len(stripped) <= 200):
        return True
    # Starts with lowercase — titles start with uppercase
    if stripped[0].islower():
        return True
    # DOI / URL lines
    if _URL_OR_DOI.search(stripped):
        return True
    # License / copyright text
    if _LICENSE_WORDS.search(stripped):
        return True
    # Institutional affiliation
    if _AFFILIATION_WORDS.search(stripped):
        return True
    # Author list
    if _is_author_line(stripped):
        return True
    return False


def _extract_title(lines: list[str], front_matter_end: int) -> str | None:
    """Return the first plausible title line in the front-matter block.

    A title candidate must:
    - Be 5–200 characters
    - Start with an uppercase letter
    - Not look like license/copyright text, a URL/DOI, an affiliation, or an author list
    """
    for line in lines[:front_matter_end]:
        stripped = line.strip()
        if not _should_skip_as_title(stripped):
            return stripped
    return None


def _extract_authors(lines: list[str], front_matter_end: int, title: str | None = None) -> list[str]:
    """Return author list from a comma-separated names line in the front matter.

    Skips the line that was already identified as the title.
    """
    for line in lines[:front_matter_end]:
        stripped = line.strip()
        if not stripped or len(stripped) < 5:
            continue
        # Skip the title line
        if title is not None and stripped == title:
            continue
        # Normalise " and " → ", "
        normalised = re.sub(r"\s+and\s+", ", ", stripped, flags=re.IGNORECASE)
        parts = [p.strip() for p in normalised.split(",") if p.strip()]
        if len(parts) < 2:
            continue
        if all(_looks_like_name(p) for p in parts):
            return parts
    return []


def _extract_doi(text: str) -> str | None:
    """Extract the first DOI found in text."""
    m = _DOI_PATTERN.search(text)
    if m:
        doi = m.group(1).rstrip(".,;)")
        return doi
    return None


def _find_front_matter_end(lines: list[str]) -> int:
    """Return index of the first section heading line (or len(lines) if none)."""
    for i, line in enumerate(lines):
        if _SECTION_HEADINGS.match(line):
            return i
    return min(len(lines), 20)  # cap at 20 lines if no heading found


def extract_metadata(full_text: str, pages: int) -> Metadata:
    """Extract structured metadata from the full document text.

    Uses heuristics:
    - Title: first substantial line before section headings
    - Authors: comma-separated names line in the front matter
    - DOI: regex match for DOI pattern anywhere in text

    Args:
        full_text: The complete extracted text of the document.
        pages: Number of pages (always propagated to Metadata.pages).

    Returns:
        A Metadata object with best-effort field values.
    """
    lines = full_text.splitlines()
    front_matter_end = _find_front_matter_end(lines)

    title = _extract_title(lines, front_matter_end)
    authors = _extract_authors(lines, front_matter_end, title=title)
    doi = _extract_doi(full_text)

    return Metadata(
        title=title,
        authors=authors,
        doi=doi,
        pages=pages,
    )
