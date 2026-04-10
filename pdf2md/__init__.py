"""pdf2md — The first open-source agentic PDF-to-markdown parser."""

__version__ = "0.1.0"

try:
    from pdf2md.core import convert, convert_batch
    from pdf2md.document import Document

    __all__ = ["convert", "convert_batch", "Document", "__version__"]
except ImportError:
    # core.py and document.py are not yet implemented; this is expected during early setup.
    __all__ = ["__version__"]
