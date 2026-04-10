"""pdf2md — The first open-source agentic PDF-to-markdown parser."""

__version__ = "0.1.0"

from pdf2md.core import convert, convert_batch
from pdf2md.document import Document

__all__ = ["convert", "convert_batch", "Document", "__version__"]
