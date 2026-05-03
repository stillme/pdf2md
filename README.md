# pdfvault

**The first open-source agentic PDF-to-markdown parser.** Extract text, tables, figures, and equations with VLM-verified accuracy. Built for researchers, knowledge workers, and document automation pipelines.

[![PyPI version](https://img.shields.io/pypi/v/pdfvault.svg)](https://pypi.org/project/pdfvault/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![GitHub stars](https://img.shields.io/github/stars/stillme/pdfvault?style=flat)](https://github.com/stillme/pdfvault)

**→ [See what we built](#what-makes-it-different) | [Quick start](#quick-start) | [Recipes](#common-tasks)**

---

## What makes it different

| | pdfvault | marker | pymupdf4llm | docling |
|---|---|---|---|---|
| **Approach** | Agentic verify-correct loop | ML pipeline | Rule-based | IBM document AI |
| **Quality guarantee** | VLM compares output to page image | None | None | None |
| **Tiers** | fast / standard / deep | Single | Single | Single |
| **Cost control** | Choose tier per document or per page | Fixed | Fixed | Fixed |
| **VLM support** | OpenAI, Anthropic, Google, Ollama | None | None | None |
| **Structured output** | Sections, tables, figures, equations, bibliography, metadata | Markdown | Markdown | DoclingDocument |

pdfvault analyzes each page's complexity and routes it to the right extraction engine. For high-stakes documents, the deep tier uses a VLM to visually compare the rendered PDF against the generated markdown, then corrects errors automatically.

### Features at a glance

- ✓ **Agentic quality verification** — VLM checks output against page images and auto-corrects
- ✓ **Tiered extraction** — fast (free), standard ($0.01/page), deep ($0.03/page), or auto
- ✓ **Smart figure extraction** — embedded images + panel grouping + captions + descriptions
- ✓ **Math support** — 60+ Unicode symbols converted to LaTeX
- ✓ **Table extraction** — with optional VLM-enhanced accuracy
- ✓ **Metadata** — title, authors, DOI parsed automatically
- ✓ **Batch processing** — corpus-scale conversion with per-paper quality reports
- ✓ **Structured output** — markdown + JSON + lightweight figure index (for ML pipelines)
- ✓ **Multiple VLM providers** — OpenAI, Anthropic, Google, Ollama
- ✓ **100% quality on Nature benchmark** — 41 pages, 15 figures, 604 math expressions

## Getting started

**Installation (2 minutes):**

```bash
pip install pdfvault
```

**Simplest possible example:**

```bash
pdfvault convert paper.pdf -o paper.md
cat paper.md
```

**Python API:**

```python
import pdfvault

# Convert a file
doc = pdfvault.convert("paper.pdf")
print(doc.markdown)

# From URL
doc = pdfvault.convert("https://arxiv.org/pdf/2301.00001.pdf")

# Structured output (not just markdown)
print(doc.metadata.title)
print(doc.metadata.authors)
for fig in doc.figures:
    print(f"Figure {fig.id}: {fig.caption}")
```

**More control:**

```bash
# Choose your tier (speed/cost tradeoff)
pdfvault convert paper.pdf --tier fast        # ~0.5s/page, free
pdfvault convert paper.pdf --tier standard    # ~2s/page, $0.01/page
pdfvault convert paper.pdf --tier deep        # ~5s/page, $0.03/page (with VLM verify-correct)

# Handle figures
pdfvault convert paper.pdf --figures extract   # Save images to disk
pdfvault convert paper.pdf --figures describe  # VLM describes each figure
pdfvault convert paper.pdf --figures skip      # Ignore figures

# Batch processing
pdfvault batch papers/ -o output/ --tier fast
```

## Common tasks

**Extract figures from a batch of research papers:**

```bash
pdfvault batch papers/*.pdf --figures extract --tier standard -o output/
# Creates: output/paper1.md, output/paper1_figures/, etc.
```

**Get just the text (no tables/figures, for speed):**

```bash
pdfvault convert paper.pdf --tier fast --figures skip
```

**Use for knowledge graph / research indexing:**

```python
import pdfvault

doc = pdfvault.convert("paper.pdf", tier="standard", figures="describe")

# Structured output for downstream tools
print(f"Title: {doc.metadata.title}")
print(f"Authors: {', '.join(doc.metadata.authors)}")
print(f"Sections: {[s.title for s in doc.sections]}")
print(f"Equations: {len(doc.equations)} math expressions")
print(f"Figures: {len(doc.figures)} figures with descriptions")

# Save everything: markdown + JSON + figure metadata
doc.save_markdown("output.md")
doc.save_json("output.json")
doc.save_figure_index("output.figures.json")  # Lightweight sidecar for ML pipelines
```

**Iterative improvement (autoresearch):**

```bash
# Runs quality scorer on Nature benchmark paper, grades 10 dimensions
uv run python autoresearch/loop.py --iterations 5
# Output: detailed quality report with strengths/weaknesses
```

---

## Features

- **Bold heading detection** — two-pass font analysis using PyMuPDF determines body text size, then detects bold text larger than body as headings. Catches Nature-style section headings that text-only detection misses, handles run-in bold headings without dropping the following sentence, and filters out title-sized text, author names, figure captions, and URLs.
- **Math/LaTeX conversion** — converts 60+ Unicode math symbols to LaTeX (`\nabla`, `\alpha`, `\sum`, etc.), wraps equations in `$...$` / `$$...$$` delimiters. Handles both display and inline equations.
- **Figure extraction** — PyMuPDF extracts embedded images (200x200+ pixels) with xref dedup and `max_per_page` filtering (keeps only the largest image per page to prevent sub-panels from counting as separate figures). pypdfium2 renders full pages as fallback. Auto MIME detection (JPEG/PNG/GIF/WebP from magic bytes) and automatic image resizing for large figures (>1500px). VLM figure descriptions available on standard/deep tiers.
- **Figure caption extraction** — Parses full figure legends from markdown text. Supports Nature style ("Fig. 1 | Caption text."), standard ("Figure 2. Caption text."), and Extended Data ("Extended Data Fig. 3 | Caption text."). Page-order caption matching prefers real captions over "See next page for caption" placeholders, synchronizes image alt text with the matched caption title, and reinserts the full caption block next to the matched figure marker.
- **Figure index sidecar** — Builds a lightweight `pdfvault.figure_index.v1` JSON artifact with figure ids, labels, captions, page/markdown anchors, panel labels, in-text panel mentions, image hashes, and parse confidence. The sidecar excludes image blobs so downstream research and knowledge-graph workflows can consume figure evidence without loading the full document JSON.
- **Panel reference parsing** — Extracts in-text references like "Fig. 3a", "Fig. 4c,d" with range expansion ("Fig. 2a--c" expands to panels a, b, c). 160 panel references found on the Nature benchmark paper.
- **Superscript reference detection** — Wraps inline citation numbers (`regions1–8` becomes `regions<sup>1–8</sup>`) and author affiliations with `<sup>` tags. Safely excludes gene names (Ang4, Defa21), CamelCase gene identifiers with comma/range-like digits, figure/table identifiers (fig1, table2), and other non-reference digit patterns.
- **Compound word hyphen handling** — Prefix/suffix-aware line-break rejoining preserves compound words (`microbiota-driven`, `region-enriched`) while correctly joining combining forms (`immunological`, `environmental`). Handles soft hyphens (U+00AD), PDF control hyphen markers (U+0002), and PDF replacement characters (U+FFBE/FFFE).
- **Figure annotation filtering** — Detects and removes figure axis labels, gene name lists, metabolite annotations, next-page caption placeholders, and statistical legend details that leak into body text from PDF figure regions. Preserves matched legend details inside explicit caption blocks and moves figure blocks to sentence boundaries when extraction interrupts prose.
- **Paragraph-flow cleanup** — Removes spurious blank lines before lowercase continuations so extracted prose does not split mid-paragraph.
- **Table extraction** — pdfplumber table detection with optional VLM correction on standard/deep tiers.
- **Agentic verify-correct loop** — deep tier uses a VLM to visually compare rendered PDF pages against generated markdown, then corrects errors automatically.
- **Metadata extraction** — title, authors, DOI parsed from document structure.
- **Numbered section detection** — recognizes patterns like "2.1 Methods" as headings.
- **Running header dedup** — ALL CAPS headers repeated on every page are collapsed to a single occurrence.

## Installation

Core (pypdfium2 + pdfplumber, no optional dependencies):

```bash
pip install pdfvault
```

All engines:

```bash
pip install pdfvault[full]
```

Individual extras:

```bash
pip install pdfvault[marker]    # ML-based document understanding
pip install pdfvault[pymupdf]   # Fast text + rendering
pip install pdfvault[docling]   # IBM document AI
pip install pdfvault[ocr]       # Tesseract + EasyOCR
```

Development:

```bash
pip install pdfvault[dev]
```

## Tiers

| Tier | What it does | VLM required | Speed | Cost |
|---|---|---|---|---|
| **fast** | pypdfium2 text extraction + pdfplumber tables. No API calls. | No | ~0.5s/page | Free |
| **standard** | Fast extraction + VLM-enhanced tables and figures. | Yes | ~2s/page | ~$0.01/page |
| **deep** | Standard + agentic verify-correct loop. VLM compares rendered page to markdown, fixes errors. | Yes | ~5s/page | ~$0.03/page |
| **auto** | Analyzes each page and selects the appropriate tier. Scanned pages get OCR, complex layouts get VLM. | Depends | Varies | Varies |

The `auto` tier (default) inspects each page for text layers, table complexity, figure density, and layout structure, then picks the cheapest tier that will produce accurate output.

On scanned pages, the `standard` and `deep` tiers route extraction through the configured VLM provider for OCR; if no VLM is available, they fall back to marker / pypdfium2.

## Benchmarks

### Extraction speed (fast tier, no VLM calls)

| Paper | Pages | Sections | Tables | Math | Figures | Time |
|-------|-------|----------|--------|------|---------|------|
| Mistral 7B arXiv paper | 9 | 12 | 0 | — | 6 | 3.7s |
| Attention Is All You Need | 15 | 32 | 8 | 24 | — | 3.3s |
| GPT-4 Technical Report | 100 | 99 | 71 | 5 | — | 8.1s |
| BERT | 16 | 51 | 8 | 5 | — | 2.1s |
| Nature (Mayassi et al. 2024) | 41 | 34 | 7 | 25 | 15 | 79s |
| DG EMI Model (math-heavy) | 30 | 16 | 6 | 604 | 5 | 6.8s |

### Quality benchmarks

The **autoresearch** quality scorer evaluates pdfvault on 10 dimensions using deterministic, pattern-based scoring (no LLM needed). Tested on the Nature gut adaptation paper (41 pages, 15 figures):

| Dimension | What it measures | Score |
|-----------|-----------------|-------|
| **figure_count** | Correct # of figures extracted (vs expected 15) | 100% |
| **figure_captions** | Caption text matched to figures | 100% |
| **figure_grouping** | Multi-panel figures kept together | 100% |
| **legend_separation** | Statistical details separated from body text | 100% |
| **body_coherence** | Prose flows without spurious breaks | 99.8% |
| **superscript_precision** | Citation numbers wrapped in `<sup>` tags | 100% |
| **headings** | Bold headings detected correctly | 100% |
| **hyphens** | Compound words preserved (microbiota-driven) | 100% |
| **completeness** | Key content phrases present | 100% |
| **metadata** | Title, authors, DOI extracted | 100% |
| **WEIGHTED TOTAL** | | **100.0%** |

Run the quality scorer yourself:

```bash
# Score the Nature paper (checks 10 dimensions)
uv run python autoresearch/loop.py --iterations 1

# Iteratively improve across 10 dimensions (runs agentic loop)
uv run python autoresearch/loop.py --iterations 10
```

### Why the Nature paper as benchmark?

The Nature paper (`s41586-024-08216-z`) is genuinely hard:
- 41 pages, 15 figures with complex panel layouts
- Mixed layout (columns, side panels, figure legends)
- 604 math symbols requiring Unicode→LaTeX conversion
- Statistical legends that need separation from body text
- Author affiliations needing superscript formatting

If pdfvault scores 100% on this, it handles the edge cases that break simpler tools.

## Providers

pdfvault supports multiple VLM providers for the standard and deep tiers. Set the provider via environment variable or argument.

**Environment variables:**

```bash
# Pick one (or more)
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export GOOGLE_API_KEY="AIza..."

# Optional: set default provider
export PDFVAULT_PROVIDER="openai/gpt-4o"
```

**Provider strings:**

```python
doc = pdfvault.convert("paper.pdf", tier="deep", provider="anthropic/claude-sonnet-4-20250514")
doc = pdfvault.convert("paper.pdf", tier="standard", provider="openai/gpt-4o")
doc = pdfvault.convert("paper.pdf", tier="standard", provider="google/gemini-2.0-flash")
doc = pdfvault.convert("paper.pdf", tier="standard", provider="ollama/llava")
```

Auto-detection: if no provider is specified, pdfvault checks for available API keys in order (Anthropic, OpenAI, Google, Ollama) and uses the first one found.

### Caching

pdfvault can cache VLM responses on disk to make repeated runs (autoresearch, benchmarks) cheap. Set `PDFVAULT_CACHE=1` to enable the content-addressed cache, keyed by `(prompt, model, image)`. Cache files default to `~/.cache/pdfvault` and the location can be overridden with `PDFVAULT_CACHE_DIR=/path`. Caching is OFF by default and never raises on read/write failures.

## CLI usage

```bash
# Convert a PDF to markdown (stdout)
pdfvault convert paper.pdf

# Write to file
pdfvault convert paper.pdf -o paper.md

# Specify tier
pdfvault convert paper.pdf --tier deep

# Figure handling
pdfvault convert paper.pdf --figures describe   # VLM describes each figure
pdfvault convert paper.pdf --figures extract     # Saves figure images to disk
pdfvault convert paper.pdf --figures skip        # Ignores figures entirely
pdfvault convert paper.pdf -o paper.md --figures-json paper.figures.json

# JSON output (includes sections, tables, metadata)
pdfvault convert paper.pdf --json

# Skip verification (faster deep tier)
pdfvault convert paper.pdf --tier deep --no-verify

# Show installed engines and configured providers
pdfvault info

# Version
pdfvault --version
```

## Python API

```python
import pdfvault

# Basic conversion
doc = pdfvault.convert("paper.pdf")

# From URL
doc = pdfvault.convert("https://arxiv.org/pdf/2301.00001.pdf")

# From bytes
with open("paper.pdf", "rb") as f:
    doc = pdfvault.convert(f.read())

# Full markdown
print(doc.markdown)

# Structured access
print(doc.metadata.title)
print(doc.metadata.authors)
print(doc.metadata.doi)

for section in doc.sections:
    print(f"  [{section.level}] {section.title} (page {section.page})")

for table in doc.tables:
    print(f"  Table {table.id}: {len(table.rows)} rows, confidence {table.confidence:.0%}")

for fig in doc.figures:
    print(f"  Figure {fig.id}: {fig.caption}")
    if fig.description:  # VLM-generated (standard/deep tier)
        print(f"    Description: {fig.description}")
    if fig.image_base64:
        print(f"    Image: {len(fig.image_base64) // 1024}KB")

for entry in doc.figure_index:
    print(f"  {entry.label}: panels={entry.panels}, mentions={len(entry.mentions)}")

# Panel references (in-text figure citations)
from pdfvault.enhancers.captions import extract_panel_references
refs = extract_panel_references(doc.markdown)
for ref in refs:
    print(f"  Fig.{ref['fig_num']} panels {ref['panels']}: {ref['context']}")

for eq in doc.equations:
    print(f"  {eq.id}: {'inline' if eq.inline else 'display'} — {eq.latex[:50]}")

# Save outputs
doc.save_markdown("output.md")
doc.save_json("output.json")
doc.save_figure_index("output.figures.json")
doc.save_figures("figures/")

# Batch conversion
docs = pdfvault.convert_batch(["a.pdf", "b.pdf", "c.pdf"], tier="fast")

# Confidence scores (deep tier)
print(f"Overall: {doc.confidence:.0%}")
for i, score in enumerate(doc.page_confidences):
    print(f"  Page {i+1}: {score:.0%}")

# Processing info
print(f"Engine: {doc.engine_used}, Tier: {doc.tier_used}, Time: {doc.processing_time_ms}ms")
```

## Integration examples

**With LangChain / LlamaIndex (RAG pipelines):**

```python
from langchain.document_loaders.base import BaseLoader
from langchain.schema import Document
import pdfvault

class PDFVaultLoader(BaseLoader):
    def __init__(self, file_path: str, tier: str = "standard"):
        self.file_path = file_path
        self.tier = tier

    def load(self) -> list[Document]:
        doc = pdfvault.convert(self.file_path, tier=self.tier)
        return [
            Document(
                page_content=doc.markdown,
                metadata={
                    "title": doc.metadata.title,
                    "authors": doc.metadata.authors,
                    "figures": len(doc.figures),
                    "source": self.file_path,
                }
            )
        ]

# Use in your RAG pipeline
loader = PDFVaultLoader("research.pdf", tier="standard")
docs = loader.load()
```

**Extracting structured data (graphs, databases):**

```python
import pdfvault
import json

doc = pdfvault.convert("paper.pdf", tier="standard", figures="describe")

# Export structured data
output = {
    "metadata": {
        "title": doc.metadata.title,
        "authors": doc.metadata.authors,
        "doi": doc.metadata.doi,
    },
    "sections": [
        {"level": s.level, "title": s.title, "content": s.content, "page": s.page}
        for s in doc.sections
    ],
    "figures": [
        {"id": f.id, "caption": f.caption, "description": f.description}
        for f in doc.figures
    ],
    "tables": [
        {"id": t.id, "rows": t.rows, "cols": t.cols}
        for t in doc.tables
    ],
}

with open("paper.structured.json", "w") as f:
    json.dump(output, f, indent=2)
```

**Batch processing with quality reports:**

```python
import pdfvault
from pathlib import Path

papers = list(Path("papers/").glob("*.pdf"))
results = []

for pdf_path in papers:
    doc = pdfvault.convert(str(pdf_path), tier="auto")
    results.append({
        "file": pdf_path.name,
        "title": doc.metadata.title,
        "pages": len(doc.page_confidences) if doc.page_confidences else 0,
        "confidence": f"{doc.confidence:.1%}" if doc.confidence else "N/A",
        "processing_time": f"{doc.processing_time_ms}ms",
        "figures": len(doc.figures),
        "tables": len(doc.tables),
    })

# Print summary
for r in results:
    print(f"{r['file']}: {r['title']} ({r['pages']} pages, {r['confidence']} confidence)")
```

---

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| `No module named 'pdfvault'` | Package not installed | `pip install pdfvault` |
| `OPENAI_API_KEY not found` | VLM provider not configured | `export OPENAI_API_KEY=sk-...` or use `--provider` |
| Extraction is slow | Using deep tier by default | Use `--tier fast` for speed, `--tier auto` to be smart |
| Figures not extracted | Scanned PDF with no text layer | Use `--tier standard` or `--tier deep` (routes to OCR) |
| Tables extracted as text | Complex layout detection failed | Try `--tier standard` for VLM-enhanced table detection |
| Math symbols are garbled | Unicode→LaTeX conversion skipped | Use `tier=standard` or higher to enable equation detection |
| Out of memory on large PDFs | Processing all pages in parallel | Reduce `max_concurrent_pages` in config |
| "Request too large" VLM error | Page image is >10MB | Reduce image size (auto-resize handles most cases) |

**Still stuck?** Check the [issues](https://github.com/stillme/pdfvault/issues) or open a new one with your PDF and the full error output.

---

## Performance tuning

**For speed (research indexing, knowledge graphs):**

```python
import pdfvault

doc = pdfvault.convert(
    "paper.pdf",
    tier="fast",                    # No VLM calls
    figures="skip",                 # Skip image extraction
    equations=False,                # Skip math symbol conversion
)
# ~0.5s/page, free
```

**For quality (high-stakes documents):**

```python
doc = pdfvault.convert(
    "paper.pdf",
    tier="deep",                    # VLM verify-correct loop
    max_verify_rounds=3,            # More iterations
    max_concurrent_pages=4,         # Single-threaded for consistency
)
# ~5s/page, ~$0.03/page
```

**For cost efficiency (default, recommended):**

```python
doc = pdfvault.convert("paper.pdf", tier="auto")
# Analyzes each page, picks the cheapest tier that works
# Fast pages stay free, complex layouts use VLM only when needed
```

**Cost breakdown (per page):**

| Tier | Cost | When to use |
|------|------|------------|
| `fast` | $0 | Speed-critical, simple layouts |
| `standard` | ~$0.01 | Balanced: quality + cost |
| `deep` | ~$0.03 | High stakes, complex documents |
| `auto` | $0–$0.03 | Default; picks tier per page |

---

## Configuration

Environment variables:

| Variable | Description | Default |
|---|---|---|
| `PDFVAULT_TIER` | Default processing tier | `auto` |
| `PDFVAULT_FIGURES` | Default figure handling mode | `caption` |
| `PDFVAULT_PROVIDER` | Default VLM provider string | Auto-detect |

Programmatic configuration:

```python
from pdfvault.config import Config, Tier, FigureMode

config = Config(
    tier=Tier.DEEP,
    figures=FigureMode.DESCRIBE,
    provider="openai/gpt-4o",
    max_verify_rounds=3,       # Agentic loop iterations (default: 2)
    max_concurrent_pages=8,    # Parallel page processing (default: 4)
    timeout_per_page=120,      # Per-page timeout in seconds (default: 60)
)
```

## Optional engines

The core package (pypdfium2 + pdfplumber) is MIT-licensed. Optional engines have their own licenses:

| Engine | Install | License | Notes |
|---|---|---|---|
| pypdfium2 | Included | Apache 2.0 / BSD | Core text extraction |
| pdfplumber | Included | MIT | Core table extraction |
| Marker | `pip install pdfvault[marker]` | GPL-3.0 | ML-based, best quality for complex layouts. GPL applies to your project if distributed. |
| PyMuPDF | `pip install pdfvault[pymupdf]` | AGPL-3.0 | Fast rendering. AGPL applies if used in a network service. |
| Docling | `pip install pdfvault[docling]` | MIT | IBM document AI |
| Tesseract | `pip install pdfvault[ocr]` | Apache 2.0 | OCR for scanned PDFs |

Check what is installed:

```bash
pdfvault info
```

## Contributing

```bash
git clone https://github.com/stillme/pdfvault
cd pdfvault
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,full]"
pytest -v
```

## License

MIT. See [LICENSE](LICENSE) for the full text.

Optional dependencies (Marker, PyMuPDF) carry their own licenses. The core package and its required dependencies are all permissively licensed.
