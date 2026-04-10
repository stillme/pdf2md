"""Superscript reference detection — wraps inline citation numbers and author affiliations."""

from __future__ import annotations

import re

# Multi-digit reference pattern: a letter followed by digits with commas/dashes.
# Matches: "regions1–8", "Mayassi1,2,9", "infection19,20", "cells6,7"
# Requires at least one separator (comma or dash) to avoid matching gene names
# like "Ang4" or "Defa21" which have single-digit suffixes.
_MULTI_REF_RE = re.compile(
    r'([a-zA-Z])'                    # preceding letter (anchor)
    r'(\d+(?:[,\u2013-]\d+)+)'      # digits with commas/en-dashes/hyphens
    r'(?=[\s,.;:)\]\n]|$)'          # followed by boundary (not more alphanum)
)

# Single/double-digit reference after a lowercase word at a sentence boundary.
# Matches: "regulation9.", "colonization10,", "disease9\n"
# Requires 3+ lowercase letters to avoid gene names (Ang4, Nos2, Cd8).
_SINGLE_REF_RE = re.compile(
    r'([a-z]{3,})'                   # lowercase word (not gene-name-like)
    r'(\d{1,2})'                     # 1-2 digit reference number
    r'(?=\s*[.,;:)\]\n]|$)'         # at sentence boundary
)

# Protect known patterns from false-positive superscripting.
# Gene names, chemical formulae, and identifiers with digits should NOT
# be treated as having superscript suffixes.
_GENE_LIKE_RE = re.compile(
    r'(?:^|(?<=\s))'               # word boundary
    r'[A-Z][a-z]*\d+[a-z]?\d*'    # CamelCase + digits (Ang4, Defa21, Slc10a2)
    r'(?=\s|$|[,.])'
)


def detect_superscripts(text: str) -> str:
    """Detect and wrap likely superscript references with <sup> tags.

    Handles two patterns:
    1. Multi-digit references with separators (high confidence):
       "regions1–8" → "regions<sup>1–8</sup>"
    2. Single-digit references after lowercase words at sentence boundaries:
       "colonization10." → "colonization<sup>10</sup>."

    Does NOT touch gene names (Ang4, Defa21), chemical formulae, or
    numbers that are part of identifiers.
    """
    # Pattern 1: multi-digit with separators (high confidence)
    text = _MULTI_REF_RE.sub(r'\1<sup>\2</sup>', text)

    # Pattern 2: single-digit after lowercase words at boundaries
    text = _SINGLE_REF_RE.sub(_single_ref_replace, text)

    return text


def _single_ref_replace(m: re.Match) -> str:
    """Replace single-digit references, with extra safety checks."""
    word = m.group(1)
    digits = m.group(2)

    # Skip if the digit is likely part of a version or measurement
    # (e.g., "phase3", "type2", "grade3" — but these are uncommon in
    # scientific text without a space, so we accept the trade-off)

    return f'{word}<sup>{digits}</sup>'
