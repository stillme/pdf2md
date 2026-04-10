"""Extractor registry — auto-detects available extraction engines."""

from __future__ import annotations
from pdf2md.extractors.base import Extractor


def get_available_extractors() -> list[Extractor]:
    extractors: list[Extractor] = []

    from pdf2md.extractors.pypdfium_ext import PypdfiumExtractor
    extractors.append(PypdfiumExtractor())

    from pdf2md.extractors.pdfplumber_ext import PdfplumberExtractor
    extractors.append(PdfplumberExtractor())

    try:
        from pdf2md.extractors.marker_ext import MarkerExtractor
        extractors.append(MarkerExtractor())
    except ImportError:
        pass

    try:
        from pdf2md.extractors.pymupdf_ext import PymupdfExtractor
        extractors.append(PymupdfExtractor())
    except ImportError:
        pass

    try:
        from pdf2md.extractors.docling_ext import DoclingExtractor
        extractors.append(DoclingExtractor())
    except ImportError:
        pass

    return extractors


def get_extractor_by_name(name: str) -> Extractor | None:
    for ext in get_available_extractors():
        if ext.name == name:
            return ext
    return None
