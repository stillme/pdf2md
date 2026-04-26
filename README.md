# pdf2md

The first open-source agentic PDF-to-markdown parser.

[![PyPI version](https://img.shields.io/pypi/v/pdf2md.svg)](https://pypi.org/project/pdf2md/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)

---

## What makes it different

| | pdf2md | marker | pymupdf4llm | docling |
|---|---|---|---|---|
| **Approach** | Agentic verify-correct loop | ML pipeline | Rule-based | IBM document AI |
| **Quality guarantee** | VLM compares output to page image | None | None | None |
| **Tiers** | fast / standard / deep | Single | Single | Single |
| **Cost control** | Choose tier per document or per page | Fixed | Fixed | Fixed |
| **VLM support** | OpenAI, Anthropic, Google, Ollama | None | None | None |
| **Structured output** | Sections, tables, figures, equations, bibliography, metadata | Markdown | Markdown | DoclingDocument |

pdf2md analyzes each page's complexity and routes it to the right extraction engine. For high-stakes documents, the deep tier uses a VLM to visually compare the rendered PDF against the generated markdown, then corrects errors automatically.

## Quick start

```python
import pdf2md

doc = pdf2md.convert("paper.pdf")
print(doc.markdown)
```

CLI:

```bash
pdf2md convert paper.pdf -o paper.md
pdf2md convert https://arxiv.org/pdf/2301.00001.pdf --tier deep
```

## Features

- **Bold heading detection** — two-pass font analysis using PyMuPDF determines body text size, then detects bold text larger than body as headings. Catches Nature-style section headings that text-only detection misses, handles run-in bold headings without dropping the following sentence, and filters out title-sized text, author names, figure captions, and URLs.
- **Math/LaTeX conversion** — converts 60+ Unicode math symbols to LaTeX (`\nabla`, `\alpha`, `\sum`, etc.), wraps equations in `$...$` / `$$...$$` delimiters. Handles both display and inline equations.
- **Figure extraction** — PyMuPDF extracts embedded images (200x200+ pixels) with xref dedup and `max_per_page` filtering (keeps only the largest image per page to prevent sub-panels from counting as separate figures). pypdfium2 renders full pages as fallback. Auto MIME detection (JPEG/PNG/GIF/WebP from magic bytes) and automatic image resizing for large figures (>1500px). VLM figure descriptions available on standard/deep tiers.
- **Figure caption extraction** — Parses full figure legends from markdown text. Supports Nature style ("Fig. 1 | Caption text."), standard ("Figure 2. Caption text."), and Extended Data ("Extended Data Fig. 3 | Caption text."). Page-order caption matching prefers real captions over "See next page for caption" placeholders, synchronizes image alt text with the matched caption title, and reinserts the full caption block next to the matched figure marker.
- **Figure index sidecar** — Builds a lightweight `pdf2md.figure_index.v1` JSON artifact with figure ids, labels, captions, page/markdown anchors, panel labels, in-text panel mentions, image hashes, and parse confidence. The sidecar excludes image blobs so downstream research and knowledge-graph workflows can consume figure evidence without loading the full document JSON.
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
pip install pdf2md
```

All engines:

```bash
pip install pdf2md[full]
```

Individual extras:

```bash
pip install pdf2md[marker]    # ML-based document understanding
pip install pdf2md[pymupdf]   # Fast text + rendering
pip install pdf2md[docling]   # IBM document AI
pip install pdf2md[ocr]       # Tesseract + EasyOCR
```

Development:

```bash
pip install pdf2md[dev]
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

## Benchmark

Tested on 6 real papers (fast tier, no VLM):

| Paper | Pages | Sections | Tables | Math | Figures | Time |
|-------|-------|----------|--------|------|---------|------|
| Mistral 7B | 9 | 12 | 0 | — | 6 | 3.7s |
| Attention Is All You Need | 15 | 32 | 8 | 24 | — | 3.3s |
| GPT-4 Technical Report | 100 | 99 | 71 | 5 | — | 8.1s |
| BERT | 16 | 51 | 8 | 5 | — | 2.1s |
| Nature (Mayassi et al. 2024) | 41 | 34 | 7 | 25 | 15 | 79s |
| DG EMI Model (math-heavy) | 30 | 16 | 6 | 604 | 5 | 6.8s |

Run your own: `pdf2md benchmark` or `pdf2md benchmark --compare` for tier comparison.

### Nature quality benchmark

The `autoresearch` harness scores the Nature Mayassi et al. paper against figure, caption, legend, body-flow, superscript, heading, hyphen, completeness, and metadata checks:

```bash
uv run python autoresearch/loop.py --agent codex --iterations 1
```

Current fast-tier output reaches 100% on all weighted dimensions except body coherence, which is at 99.8%; the weighted total rounds to 100.0%.

## Providers

pdf2md supports multiple VLM providers for the standard and deep tiers. Set the provider via environment variable or argument.

**Environment variables:**

```bash
# Pick one (or more)
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export GOOGLE_API_KEY="AIza..."

# Optional: set default provider
export PDF2MD_PROVIDER="openai/gpt-4o"
```

**Provider strings:**

```python
doc = pdf2md.convert("paper.pdf", tier="deep", provider="anthropic/claude-sonnet-4-20250514")
doc = pdf2md.convert("paper.pdf", tier="standard", provider="openai/gpt-4o")
doc = pdf2md.convert("paper.pdf", tier="standard", provider="google/gemini-2.0-flash")
doc = pdf2md.convert("paper.pdf", tier="standard", provider="ollama/llava")
```

Auto-detection: if no provider is specified, pdf2md checks for available API keys in order (Anthropic, OpenAI, Google, Ollama) and uses the first one found.

### Caching

pdf2md can cache VLM responses on disk to make repeated runs (autoresearch, benchmarks) cheap. Set `PDF2MD_CACHE=1` to enable the content-addressed cache, keyed by `(prompt, model, image)`. Cache files default to `~/.cache/pdf2md` and the location can be overridden with `PDF2MD_CACHE_DIR=/path`. Caching is OFF by default and never raises on read/write failures.

## CLI usage

```bash
# Convert a PDF to markdown (stdout)
pdf2md convert paper.pdf

# Write to file
pdf2md convert paper.pdf -o paper.md

# Specify tier
pdf2md convert paper.pdf --tier deep

# Figure handling
pdf2md convert paper.pdf --figures describe   # VLM describes each figure
pdf2md convert paper.pdf --figures extract     # Saves figure images to disk
pdf2md convert paper.pdf --figures skip        # Ignores figures entirely
pdf2md convert paper.pdf -o paper.md --figures-json paper.figures.json

# JSON output (includes sections, tables, metadata)
pdf2md convert paper.pdf --json

# Skip verification (faster deep tier)
pdf2md convert paper.pdf --tier deep --no-verify

# Show installed engines and configured providers
pdf2md info

# Version
pdf2md --version
```

## Python API

```python
import pdf2md

# Basic conversion
doc = pdf2md.convert("paper.pdf")

# From URL
doc = pdf2md.convert("https://arxiv.org/pdf/2301.00001.pdf")

# From bytes
with open("paper.pdf", "rb") as f:
    doc = pdf2md.convert(f.read())

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
from pdf2md.enhancers.captions import extract_panel_references
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
docs = pdf2md.convert_batch(["a.pdf", "b.pdf", "c.pdf"], tier="fast")

# Confidence scores (deep tier)
print(f"Overall: {doc.confidence:.0%}")
for i, score in enumerate(doc.page_confidences):
    print(f"  Page {i+1}: {score:.0%}")

# Processing info
print(f"Engine: {doc.engine_used}, Tier: {doc.tier_used}, Time: {doc.processing_time_ms}ms")
```

## Configuration

Environment variables:

| Variable | Description | Default |
|---|---|---|
| `PDF2MD_TIER` | Default processing tier | `auto` |
| `PDF2MD_FIGURES` | Default figure handling mode | `caption` |
| `PDF2MD_PROVIDER` | Default VLM provider string | Auto-detect |

Programmatic configuration:

```python
from pdf2md.config import Config, Tier, FigureMode

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
| Marker | `pip install pdf2md[marker]` | GPL-3.0 | ML-based, best quality for complex layouts. GPL applies to your project if distributed. |
| PyMuPDF | `pip install pdf2md[pymupdf]` | AGPL-3.0 | Fast rendering. AGPL applies if used in a network service. |
| Docling | `pip install pdf2md[docling]` | MIT | IBM document AI |
| Tesseract | `pip install pdf2md[ocr]` | Apache 2.0 | OCR for scanned PDFs |

Check what is installed:

```bash
pdf2md info
```

## Contributing

```bash
git clone https://github.com/stillme/pdf2md
cd pdf2md
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,full]"
pytest -v
```

## License

MIT. See [LICENSE](LICENSE) for the full text.

Optional dependencies (Marker, PyMuPDF) carry their own licenses. The core package and its required dependencies are all permissively licensed.
