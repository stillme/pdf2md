"""Unicode normalization — soft hyphens, ligatures, and stray control characters.

Scientific PDFs frequently encode discretionary hyphens as ``\\xad`` or ``\\x02``
depending on the font, and use the FB00–FB06 ligature glyphs (``­``-aware
fonts) for ``fi``/``fl``/``ff`` etc. Both leak through every text extractor we
support and corrupt downstream consumers (metadata regex, bibliography parser,
caption matcher). This module is the single normalization step run early in the
pipeline so every later stage sees clean text.
"""

from __future__ import annotations

import re

# Soft-hyphen characters seen in the wild. ``\xad`` is the official Unicode
# soft hyphen; ``\x02`` is what some PostScript fonts (notably Nature's body
# font) emit for the same glyph.
_SOFT_HYPHENS = "\xad\x02"

_LIGATURES = {
    "ﬀ": "ff",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
    "ﬅ": "ft",
    "ﬆ": "st",
}

# Match a soft hyphen surrounded by word characters on both sides — these
# are mid-word breaks (``micro­biota``) where the original word had a real
# hyphen rendered as a discretionary break.
_SOFT_HYPHEN_BETWEEN_LETTERS = re.compile(rf"(?<=\w)[{_SOFT_HYPHENS}](?=\w)")
# Anything else (end of line, before punctuation, etc.) is line-break
# hyphenation that should be dropped.
_SOFT_HYPHEN_ANY = re.compile(rf"[{_SOFT_HYPHENS}]")

# C0 control characters except tab/newline/carriage-return. Soft-hyphen
# handling above already consumed ``\x02``; the rest are extraction noise
# (BEL, ESC, form-feed) that bloat downstream regex matches.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

_LIGATURE_RE = re.compile("[" + "".join(_LIGATURES.keys()) + "]")


def normalize_unicode_text(text: str) -> str:
    """Normalize PDF text artifacts: soft hyphens, ligatures, control chars.

    - Soft hyphens between letters become real hyphens (``micro­biota`` →
      ``micro-biota``); soft hyphens elsewhere are stripped (``end-of-line­\\n``
      → ``end-of-line\\n``).
    - FB00–FB06 ligature glyphs expand to their letter equivalents.
    - C0 control characters (except tab/newline/carriage-return) are removed.
    - Idempotent: applying twice yields the same result as once.
    """
    if not text:
        return text

    text = _SOFT_HYPHEN_BETWEEN_LETTERS.sub("-", text)
    text = _SOFT_HYPHEN_ANY.sub("", text)
    text = _LIGATURE_RE.sub(lambda m: _LIGATURES[m.group(0)], text)
    text = _CONTROL_CHARS.sub("", text)
    return text
