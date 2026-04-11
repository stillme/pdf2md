"""Enhancers package — VLM-powered figure, table, and math enhancement."""
from pdf2md.enhancers.figures import enhance_figures
from pdf2md.enhancers.math import convert_unicode_math, extract_equations_vlm
from pdf2md.enhancers.superscripts import detect_superscripts
from pdf2md.enhancers.tables import enhance_table
from pdf2md.enhancers.text_cleaner import clean_figure_text

__all__ = [
    "enhance_figures",
    "enhance_table",
    "convert_unicode_math",
    "extract_equations_vlm",
    "clean_figure_text",
    "detect_superscripts",
]
