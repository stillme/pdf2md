"""Tests for math/LaTeX enhancer."""
from unittest.mock import MagicMock

from pdf2md.enhancers.math import (
    UNICODE_TO_LATEX,
    convert_unicode_math,
    detect_math_regions,
    extract_equations_vlm,
)
from pdf2md.document import Equation


# ── Unicode → LaTeX basic conversion ─────────────────────────────────

def test_unicode_to_latex_basic():
    text = "The gradient ∇f equals zero."
    result = convert_unicode_math(text)
    assert r"\nabla" in result
    assert "∇" not in result


def test_display_equation():
    text = "We solve:\n−∇ · (κ∇u) = f\nwhere f is given."
    result = convert_unicode_math(text)
    assert "$$" in result  # Display math wrapping
    assert r"\nabla" in result
    assert r"\kappa" in result


def test_inline_math():
    text = "For all x ∈ Ω we have u ≤ M."
    result = convert_unicode_math(text)
    assert "$" in result
    assert r"\in" in result
    assert r"\leq" in result


def test_no_math_unchanged():
    text = "This is a plain English sentence with no math."
    result = convert_unicode_math(text)
    assert result == text


def test_greek_letters():
    text = "The parameters α, β, and γ control the model."
    result = convert_unicode_math(text)
    assert r"\alpha" in result
    assert r"\beta" in result
    assert r"\gamma" in result


def test_norm_symbol():
    text = "The norm ∥u∥ is bounded."
    result = convert_unicode_math(text)
    assert r"\|" in result
    assert "∥" not in result


def test_multiple_symbols_per_line():
    text = "If x ∈ Ω and ∇u ≠ 0 then..."
    result = convert_unicode_math(text)
    assert r"\in" in result
    assert r"\nabla" in result
    assert r"\neq" in result
    assert "∈" not in result
    assert "∇" not in result
    assert "≠" not in result


def test_already_has_dollar_delimiters():
    """Text that already has LaTeX delimiters should not be double-wrapped."""
    text = "We know that $\\nabla f = 0$ holds."
    result = convert_unicode_math(text)
    # Should be unchanged — no unicode math to convert
    assert result == text


def test_preserves_non_math_lines():
    text = "Introduction\n\nThis paper studies PDEs.\n∇²u = f\nThe end."
    result = convert_unicode_math(text)
    lines = result.split("\n")
    assert lines[0] == "Introduction"
    assert "This paper studies PDEs." in result
    assert "The end." in result


# ── detect_math_regions ──────────────────────────────────────────────

def test_detect_math_regions():
    text = "Normal text.\n∇ · (κ∇u) = f\nMore normal text.\nThe value α ∈ [0,1]."
    regions = detect_math_regions(text)
    assert len(regions) >= 2


def test_detect_math_regions_none():
    text = "No math symbols here at all. Just plain English."
    regions = detect_math_regions(text)
    assert len(regions) == 0


def test_detect_math_regions_single_symbol():
    """A line with only one math symbol should NOT be detected as a math region."""
    text = "A simple line with α in it."
    regions = detect_math_regions(text)
    # 1 symbol is below the threshold of 2
    assert len(regions) == 0


# ── VLM equation extraction ─────────────────────────────────────────

def test_vlm_equation_extraction():
    mock_provider = MagicMock()
    mock_provider.complete_sync.return_value = (
        "DISPLAY: $$-\\nabla \\cdot (\\kappa_e \\nabla u_e) = f_e$$\n"
        "INLINE: $\\Omega_e \\times (0, T)$\n"
    )

    equations = extract_equations_vlm(
        page_image=b"fake",
        page_text="−∇ · (κe∇ue) = fe in Ωe × (0, T)",
        provider=mock_provider,
    )
    assert len(equations) >= 1
    assert any("nabla" in eq.latex for eq in equations)


def test_vlm_equation_extraction_display_type():
    mock_provider = MagicMock()
    mock_provider.complete_sync.return_value = (
        "DISPLAY: $$\\int_0^1 f(x) dx = 1$$\n"
    )

    equations = extract_equations_vlm(
        page_image=b"fake",
        page_text="∫₀¹ f(x) dx = 1",
        provider=mock_provider,
    )
    assert len(equations) == 1
    assert equations[0].inline is False
    assert "int" in equations[0].latex


def test_vlm_equation_extraction_inline_type():
    mock_provider = MagicMock()
    mock_provider.complete_sync.return_value = "INLINE: $x \\in \\Omega$\n"

    equations = extract_equations_vlm(
        page_image=b"fake",
        page_text="x ∈ Ω",
        provider=mock_provider,
    )
    assert len(equations) == 1
    assert equations[0].inline is True


def test_vlm_no_math_skips_call():
    """If the page text has no math symbols, VLM should not be called."""
    mock_provider = MagicMock()

    equations = extract_equations_vlm(
        page_image=b"fake",
        page_text="This is plain text with no math.",
        provider=mock_provider,
    )
    assert len(equations) == 0
    mock_provider.complete_sync.assert_not_called()


def test_vlm_equation_with_number():
    mock_provider = MagicMock()
    mock_provider.complete_sync.return_value = (
        "DISPLAY: $$-\\nabla \\cdot (\\kappa \\nabla u) = f \\quad (2.1)$$\n"
    )

    equations = extract_equations_vlm(
        page_image=b"fake",
        page_text="−∇ · (κ∇u) = f    (2.1)",
        provider=mock_provider,
    )
    assert len(equations) == 1
    assert "(2.1)" in equations[0].latex


def test_vlm_malformed_response():
    """VLM returns garbage — should return empty list, not crash."""
    mock_provider = MagicMock()
    mock_provider.complete_sync.return_value = "I don't see any equations."

    equations = extract_equations_vlm(
        page_image=b"fake",
        page_text="∇u = 0",
        provider=mock_provider,
    )
    assert isinstance(equations, list)


# ── Unicode map completeness ─────────────────────────────────────────

def test_unicode_map_has_greek():
    assert "α" in UNICODE_TO_LATEX
    assert "Ω" in UNICODE_TO_LATEX
    assert UNICODE_TO_LATEX["α"] == r"\alpha"
    assert UNICODE_TO_LATEX["Ω"] == r"\Omega"


def test_unicode_map_has_operators():
    for sym in ["∇", "∂", "∑", "∫", "∈", "≤", "≥", "≠", "±", "×", "·", "∞"]:
        assert sym in UNICODE_TO_LATEX
