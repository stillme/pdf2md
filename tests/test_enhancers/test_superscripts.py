"""Tests for superscript reference detection."""

from pdf2md.enhancers.superscripts import detect_superscripts


# --- Multi-digit references (high confidence) ---

def test_multi_ref_with_en_dash():
    """Citation ranges like 'regions1–8' should get <sup> tags."""
    assert detect_superscripts("regions1\u20138\n") == "regions<sup>1\u20138</sup>\n"


def test_multi_ref_with_commas():
    """Author affiliations like 'Mayassi1,2,9' should get <sup> tags."""
    text = "Mayassi1,2,9, Li1,2,3,"
    result = detect_superscripts(text)
    assert "Mayassi<sup>1,2,9</sup>" in result
    assert "Li<sup>1,2,3</sup>" in result


def test_multi_ref_mixed_commas_and_dashes():
    """Mixed separators like 'genes6,7' should be handled."""
    assert detect_superscripts("genes6,7,") == "genes<sup>6,7</sup>,"


def test_multi_ref_at_end_of_sentence():
    """References before a period: 'infection19,20.'"""
    result = detect_superscripts("infection19,20.")
    assert result == "infection<sup>19,20</sup>."


# --- Single-digit references ---

def test_single_ref_before_newline():
    """Single digit ref at end of line: 'regulation9\\n'"""
    result = detect_superscripts("regulation9\n")
    assert result == "regulation<sup>9</sup>\n"


def test_single_ref_before_period():
    """Single digit ref before period: 'disease9.'"""
    result = detect_superscripts("disease9.")
    assert result == "disease<sup>9</sup>."


def test_single_ref_two_digits():
    """Two-digit ref: 'colonization10,'"""
    result = detect_superscripts("colonization10,")
    assert result == "colonization<sup>10</sup>,"


# --- Should NOT match ---

def test_no_match_gene_names():
    """Gene names like Ang4, Defa21 should NOT get <sup> tags."""
    text = "Ang4 Defa21 Slc10a2 Nos2 Cd8a"
    result = detect_superscripts(text)
    # Gene names start with uppercase, single-ref pattern requires 3+ lowercase
    assert "<sup>" not in result


def test_no_match_numbers_with_commas():
    """Formatted numbers like '138,243' should NOT be superscripted."""
    text = "a total of 138,243 spots"
    result = detect_superscripts(text)
    assert "138,243" in result
    assert "<sup>" not in result


def test_no_match_standalone_numbers():
    """Standalone numbers: '0.5', '1000' should NOT be superscripted."""
    text = "measured 0.5 and 1000 units"
    result = detect_superscripts(text)
    assert "<sup>" not in result


def test_no_match_gene_name_il17():
    """IL17 and similar identifiers should NOT match."""
    text = "IL17 expression was measured."
    result = detect_superscripts(text)
    assert "<sup>" not in result


def test_no_match_camelcase_gene_with_multi_reference_shape():
    """CamelCase genes with comma-separated digits should not look like citations."""
    text = "Calca38,41 Hoxb13 Itln1 Tcf7l1 were measured."
    result = detect_superscripts(text)
    assert result == text


def test_no_match_short_words():
    """Words shorter than 3 lowercase chars shouldn't trigger single-ref."""
    text = "in2. or3."
    result = detect_superscripts(text)
    # "in" is only 2 lowercase chars, "or" is only 2 — shouldn't match
    assert "<sup>" not in result


def test_no_match_figure_identifier():
    """Figure identifiers like 'fig1', 'fig2' should NOT get <sup> tags."""
    text = "As shown in fig1. The data in fig2 demonstrates."
    result = detect_superscripts(text)
    assert "fig1" in result
    assert "fig2" in result
    assert "fig<sup>" not in result


def test_no_match_table_identifier():
    """Table identifiers like 'tab1', 'table1' should NOT get <sup> tags."""
    text = "Results in tab1. Data from table2 shows."
    result = detect_superscripts(text)
    assert "tab1" in result
    assert "table2" in result
    assert "tab<sup>" not in result
    assert "table<sup>" not in result


def test_no_match_equation_identifier():
    """Equation identifiers like 'eq1', 'equation2' should NOT get <sup> tags."""
    text = "Using eq1. The formula in equation3 shows."
    result = detect_superscripts(text)
    assert "eq1" in result
    assert "equation3" in result
    assert "eq<sup>" not in result
    assert "equation<sup>" not in result


def test_no_match_supplementary_identifier():
    """Supplementary identifiers like 'supp1' should NOT get <sup> tags."""
    text = "Additional data in supp1. See supplementary2 for details."
    result = detect_superscripts(text)
    assert "supp1" in result
    assert "supplementary2" in result
    assert "supp<sup>" not in result
    assert "supplementary<sup>" not in result


# --- Preserves surrounding text ---

def test_preserves_surrounding_text():
    """The rest of the text around superscripts should be unchanged."""
    text = "We identified cells from different intestinal regions1\u20138. However, more work is needed."
    result = detect_superscripts(text)
    assert "We identified cells from different intestinal" in result
    assert "regions<sup>1\u20138</sup>" in result
    assert "However, more work is needed." in result


def test_multiple_refs_in_one_line():
    """Multiple references on one line should all be detected."""
    text = "confirmed by studies19,20 and reviews1,2,3."
    result = detect_superscripts(text)
    assert "studies<sup>19,20</sup>" in result
    assert "reviews<sup>1,2,3</sup>" in result


def test_empty_text():
    """Empty input should return empty."""
    assert detect_superscripts("") == ""
