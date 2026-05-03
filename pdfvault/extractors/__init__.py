"""Extractor registry — auto-detects available extraction engines."""

from __future__ import annotations
from pdfvault.extractors.base import Extractor


def get_available_extractors() -> list[Extractor]:
    extractors: list[Extractor] = []

    from pdfvault.extractors.pypdfium_ext import PypdfiumExtractor
    extractors.append(PypdfiumExtractor())

    from pdfvault.extractors.pdfplumber_ext import PdfplumberExtractor
    extractors.append(PdfplumberExtractor())

    try:
        from pdfvault.extractors.marker_ext import MarkerExtractor
        extractors.append(MarkerExtractor())
    except ImportError:
        pass

    try:
        from pdfvault.extractors.pymupdf_ext import PymupdfExtractor
        extractors.append(PymupdfExtractor())
    except ImportError:
        pass

    try:
        from pdfvault.extractors.docling_ext import DoclingExtractor
        extractors.append(DoclingExtractor())
    except ImportError:
        pass

    return extractors


def get_extractor_by_name(name: str) -> Extractor | None:
    for ext in get_available_extractors():
        if ext.name == name:
            return ext
    return None
