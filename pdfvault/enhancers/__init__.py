"""Enhancers package — VLM-powered figure, table, and math enhancement."""
from pdfvault.enhancers.cross_references import add_cross_references
from pdfvault.enhancers.figures import enhance_figures
from pdfvault.enhancers.math import convert_unicode_math, extract_equations_vlm
from pdfvault.enhancers.references import parse_references
from pdfvault.enhancers.superscripts import detect_superscripts
from pdfvault.enhancers.tables import enhance_table
from pdfvault.enhancers.text_cleaner import clean_figure_text
from pdfvault.enhancers.unicode_normalizer import normalize_unicode_text

__all__ = [
    "add_cross_references",
    "enhance_figures",
    "enhance_table",
    "convert_unicode_math",
    "extract_equations_vlm",
    "clean_figure_text",
    "detect_superscripts",
    "normalize_unicode_text",
    "parse_references",
]
