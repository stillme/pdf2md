"""Math/LaTeX enhancer — Unicode→LaTeX conversion and VLM equation extraction."""

from __future__ import annotations

import re
from dataclasses import dataclass

from pdf2md.document import Equation
from pdf2md.providers.base import VLMProvider

# ── Unicode → LaTeX character mapping ────────────────────────────────

UNICODE_TO_LATEX: dict[str, str] = {
    # Operators & relations
    "∇": r"\nabla",
    "∂": r"\partial",
    "∑": r"\sum",
    "∫": r"\int",
    "∈": r"\in",
    "∉": r"\notin",
    "⊂": r"\subset",
    "⊃": r"\supset",
    "⊆": r"\subseteq",
    "⊇": r"\supseteq",
    "∪": r"\cup",
    "∩": r"\cap",
    "∀": r"\forall",
    "∃": r"\exists",
    "→": r"\to",
    "←": r"\leftarrow",
    "↔": r"\leftrightarrow",
    "⇒": r"\Rightarrow",
    "⇐": r"\Leftarrow",
    "⇔": r"\Leftrightarrow",
    "≤": r"\leq",
    "≥": r"\geq",
    "≈": r"\approx",
    "≡": r"\equiv",
    "≠": r"\neq",
    "±": r"\pm",
    "∓": r"\mp",
    "×": r"\times",
    "÷": r"\div",
    "·": r"\cdot",
    "∞": r"\infty",
    "√": r"\sqrt",
    "∥": r"\|",
    "⊗": r"\otimes",
    "⊕": r"\oplus",
    "∝": r"\propto",
    "∅": r"\emptyset",
    "¬": r"\neg",
    "∧": r"\wedge",
    "∨": r"\vee",
    "⊥": r"\perp",
    "∘": r"\circ",
    "†": r"\dagger",
    "‡": r"\ddagger",
    "ℓ": r"\ell",
    "ℏ": r"\hbar",
    "ℵ": r"\aleph",
    "−": r"-",
    "′": r"'",
    "″": r"''",
    # Greek lowercase
    "α": r"\alpha",
    "β": r"\beta",
    "γ": r"\gamma",
    "δ": r"\delta",
    "ε": r"\varepsilon",
    "ζ": r"\zeta",
    "η": r"\eta",
    "θ": r"\theta",
    "ι": r"\iota",
    "κ": r"\kappa",
    "λ": r"\lambda",
    "μ": r"\mu",
    "ν": r"\nu",
    "ξ": r"\xi",
    "π": r"\pi",
    "ρ": r"\rho",
    "σ": r"\sigma",
    "τ": r"\tau",
    "υ": r"\upsilon",
    "φ": r"\varphi",
    "χ": r"\chi",
    "ψ": r"\psi",
    "ω": r"\omega",
    # Greek uppercase
    "Γ": r"\Gamma",
    "Δ": r"\Delta",
    "Θ": r"\Theta",
    "Λ": r"\Lambda",
    "Ξ": r"\Xi",
    "Π": r"\Pi",
    "Σ": r"\Sigma",
    "Φ": r"\Phi",
    "Ψ": r"\Psi",
    "Ω": r"\Omega",
}

# Unicode subscript and superscript digits — recognized as math context
# for detection purposes (not converted; VLM handles them).
_UNICODE_SUB_SUPER: set[str] = set(
    "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎"
    "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ"
)

# Build the set of all recognized math Unicode characters for detection.
_MATH_CHARS: set[str] = set(UNICODE_TO_LATEX.keys()) | _UNICODE_SUB_SUPER

# Minimum number of math symbols on a line for it to count as a "math region".
_MIN_MATH_SYMBOLS = 2

# "Heavy" math operators — a single one of these is enough to trigger conversion
# when it appears adjacent to variable-like text (e.g., "∇f").
_HEAVY_MATH_OPS: set[str] = {
    "∇", "∂", "∑", "∫", "∀", "∃", "∥", "√",
}

# ── VLM prompt ───────────────────────────────────────────────────────

_EQUATION_EXTRACTION_PROMPT = """\
This PDF page contains mathematical equations. Convert each equation to LaTeX notation.

For each equation found, output it in this format:
DISPLAY: $$latex_here$$
or
INLINE: $latex_here$

Only output the equations, one per line. Include equation numbers if present (e.g., (2.1))."""


# ── Helpers ──────────────────────────────────────────────────────────

@dataclass
class MathRegion:
    """A contiguous region of text that contains math symbols."""
    line_number: int
    text: str
    symbol_count: int


def _count_math_symbols(text: str) -> int:
    """Count the number of math Unicode symbols in a string."""
    return sum(1 for ch in text if ch in _MATH_CHARS)


def _is_display_math(line: str) -> bool:
    """Determine whether a line is pure display math (no substantial English).

    A line is display math if:
    - It has math symbols, AND
    - The non-math, non-punctuation, non-digit content is very short
      (single-letter variables, operators, etc., but no English words of 4+ chars).
    """
    # Strip leading/trailing whitespace
    stripped = line.strip()
    if not stripped:
        return False

    # Split into words and check for English content
    words = stripped.split()
    english_word_count = 0
    for word in words:
        # Clean punctuation from word edges
        clean = word.strip("()[]{}.,;:=<>!?")
        # A "word" is English if it's 4+ alphabetic characters with no math symbols
        if len(clean) >= 4 and clean.isalpha() and not any(c in _MATH_CHARS for c in clean):
            english_word_count += 1

    # If there are no substantial English words, it's display math
    return english_word_count == 0


def _replace_unicode_in_span(text: str) -> str:
    """Replace all Unicode math characters with their LaTeX equivalents."""
    result = []
    for ch in text:
        if ch in UNICODE_TO_LATEX:
            latex = UNICODE_TO_LATEX[ch]
            # Add space around LaTeX commands so they don't merge with adjacent text
            # e.g., "∇f" -> "\nabla f" not "\nablaf"
            if latex.startswith("\\") and len(latex) > 2:
                result.append(f" {latex} ")
            else:
                result.append(latex)
        else:
            result.append(ch)
    # Collapse multiple spaces
    return re.sub(r"  +", " ", "".join(result)).strip()


def _line_already_delimited(line: str) -> bool:
    """Check if a line already contains $...$ or $$...$$ delimiters."""
    stripped = line.strip()
    return "$" in stripped


# ── Public API ───────────────────────────────────────────────────────

def detect_math_regions(text: str) -> list[MathRegion]:
    """Identify lines that contain 2+ math Unicode symbols.

    Returns a list of MathRegion objects, one per qualifying line.
    """
    regions: list[MathRegion] = []
    for i, line in enumerate(text.splitlines()):
        count = _count_math_symbols(line)
        if count >= _MIN_MATH_SYMBOLS:
            regions.append(MathRegion(line_number=i, text=line, symbol_count=count))
    return regions


def convert_unicode_math(text: str) -> str:
    """Convert Unicode math symbols in text to LaTeX with proper delimiters.

    Lines with 2+ math symbols are wrapped in $...$ (inline) or $$...$$ (display).
    Lines with fewer symbols or no symbols are left unchanged.
    """
    lines = text.splitlines()
    result_lines: list[str] = []

    for line in lines:
        count = _count_math_symbols(line)

        # Check for heavy operator (single symbol like ∇ is enough)
        has_heavy = any(ch in _HEAVY_MATH_OPS for ch in line)

        # No math symbols or already delimited — leave unchanged
        if (count < _MIN_MATH_SYMBOLS and not has_heavy) or _line_already_delimited(line):
            result_lines.append(line)
            continue

        # Convert the Unicode symbols to LaTeX
        converted = _replace_unicode_in_span(line)

        if _is_display_math(line):
            # Pure math line → display math
            result_lines.append(f"$${converted}$$")
        else:
            # Mixed math + English → wrap math segments inline
            result_lines.append(_wrap_inline_math(line))

    return "\n".join(result_lines)


def _wrap_inline_math(line: str) -> str:
    """Wrap math-symbol-containing segments of a line in inline $...$ delimiters.

    Scans the line for contiguous runs that contain math symbols and wraps
    those runs. Leaves non-math words as plain text.
    """
    # Strategy: split line into tokens, group adjacent tokens that contain
    # math symbols, and wrap each group.
    tokens = line.split()
    result_parts: list[str] = []
    math_buffer: list[str] = []

    def flush_math():
        if math_buffer:
            raw = " ".join(math_buffer)
            converted = _replace_unicode_in_span(raw)
            result_parts.append(f"${converted}$")
            math_buffer.clear()

    for token in tokens:
        has_math = any(ch in _MATH_CHARS for ch in token)
        if has_math:
            math_buffer.append(token)
        else:
            # Check if this token is a short connector between math tokens
            # (e.g., single-letter variables, "=", numbers)
            is_connector = (
                len(math_buffer) > 0
                and len(token) <= 2
                and not token[0].isupper()
            )
            if is_connector:
                math_buffer.append(token)
            else:
                flush_math()
                result_parts.append(token)

    flush_math()
    return " ".join(result_parts)


def extract_equations_vlm(
    page_image: bytes,
    page_text: str,
    provider: VLMProvider,
    *,
    page_number: int = 0,
) -> list[Equation]:
    """Extract equations from a PDF page image using a VLM.

    Args:
        page_image: PNG bytes of the rendered page.
        page_text: The text-layer content of the page (used to detect math).
        provider: A VLM provider implementing complete_sync().
        page_number: The page number (0-indexed) for tagging equations.

    Returns:
        A list of Equation objects parsed from the VLM response.
    """
    # Skip VLM call if the page has no math symbols
    if _count_math_symbols(page_text) < _MIN_MATH_SYMBOLS:
        return []

    # Send page image + prompt to VLM
    response = provider.complete_sync(_EQUATION_EXTRACTION_PROMPT, image=page_image)

    # Parse the VLM response into Equation objects
    return _parse_vlm_equations(response, page_number=page_number)


def _parse_vlm_equations(response: str, page_number: int = 0) -> list[Equation]:
    """Parse VLM response lines into Equation objects.

    Expected format per line:
        DISPLAY: $$latex_here$$
        INLINE: $latex_here$
    """
    equations: list[Equation] = []
    eq_counter = 0

    for line in response.strip().splitlines():
        line = line.strip()
        if not line:
            continue

        inline = False
        latex = ""

        if line.startswith("DISPLAY:"):
            raw = line[len("DISPLAY:"):].strip()
            # Strip $$ delimiters
            latex = raw.strip("$").strip()
            inline = False
        elif line.startswith("INLINE:"):
            raw = line[len("INLINE:"):].strip()
            # Strip $ delimiters
            latex = raw.strip("$").strip()
            inline = True
        else:
            # Unrecognised format — skip
            continue

        if not latex:
            continue

        eq_counter += 1
        equations.append(
            Equation(
                id=f"eq{page_number + 1}_{eq_counter}",
                latex=latex,
                inline=inline,
                context=None,
                page=page_number,
            )
        )

    return equations
