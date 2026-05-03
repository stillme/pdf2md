"""pdfvault — The first open-source agentic PDF-to-markdown parser."""

__version__ = "0.1.0"

from pdfvault.batch import BatchSummary, PaperResult, run_batch
from pdfvault.core import convert, convert_batch
from pdfvault.document import Document

__all__ = [
    "BatchSummary",
    "Document",
    "PaperResult",
    "__version__",
    "convert",
    "convert_batch",
    "run_batch",
]
