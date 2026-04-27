"""pdf2md — The first open-source agentic PDF-to-markdown parser."""

__version__ = "0.1.0"

from pdf2md.batch import BatchSummary, PaperResult, run_batch
from pdf2md.core import convert, convert_batch
from pdf2md.document import Document

__all__ = [
    "BatchSummary",
    "Document",
    "PaperResult",
    "__version__",
    "convert",
    "convert_batch",
    "run_batch",
]
