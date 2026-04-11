---
name: pdf
description: Convert PDFs to structured markdown with math/LaTeX, run-in bold heading detection, figure extraction with sub-panel filtering, page-order full-caption matching, lightweight figure-index sidecars, superscript reference detection, compound hyphen handling, legend cleanup, and agentic verification. Handles scientific papers, Nature articles, and math-heavy documents.
---

Convert a PDF to markdown using pdf2md.

## Usage

/pdf <file_path_or_url> [options]

Examples:
- /pdf paper.pdf
- /pdf paper.pdf --deep
- /pdf paper.pdf --figures describe
- /pdf https://arxiv.org/pdf/2301.00001.pdf
- /pdf benchmark
- /pdf benchmark --compare

## How It Works

1. Check if pdf2md is installed; if not, offer to install it
2. Run conversion with the specified options
3. Math/LaTeX conversion runs automatically on all tiers (60+ Unicode symbols mapped to LaTeX, display/inline equation wrapping)
4. Bold heading detection runs automatically when PyMuPDF is installed (two-pass font analysis catches Nature-style section headings, run-in bold headings, and filters out title-sized text)
5. Figure extraction uses PyMuPDF embedded images with xref dedup, max_per_page filtering (keeps only the largest image per page to prevent sub-panels from counting as separate figures), auto MIME detection (JPEG/PNG/GIF/WebP), and automatic resizing for large images. Caption extraction supports Nature ("|"), standard ("."), and Extended Data styles; page-order caption matching prefers real captions over "See next page" placeholders, syncs image alt text to the matched caption title, and reinserts the full legend block next to the matched figure marker. Panel references (e.g., "Fig. 3a", "Fig. 4c,d", "Extended Data Fig. 2a-c") are parsed with range expansion. `doc.figure_index` and `doc.save_figure_index()` expose a lightweight `pdf2md.figure_index.v1` JSON sidecar with labels, captions, panel labels, body mentions, page/markdown anchors, image hashes, and parse confidence, without embedding image blobs. VLM figure descriptions remain available on standard/deep tiers
6. Superscript reference detection wraps inline citation numbers and author affiliations with `<sup>` tags while excluding gene names, CamelCase gene identifiers with comma/range-like digits, figure identifiers, and other non-reference patterns
7. Compound word hyphen handling preserves hyphens in compound words (microbiota-driven) while joining combining forms (immunological), including PDF control hyphen markers. Figure annotation filtering removes leaked axis labels, metabolite names, next-page caption placeholders, and statistical legend details from body text while preserving matched details inside explicit caption blocks. Paragraph-flow cleanup removes spurious blank lines before lowercase continuations and moves figure blocks to sentence boundaries when extraction interrupts prose
8. Return the markdown directly into the conversation context
9. For deep tier, show confidence scores

## Implementation

When the user invokes /pdf:

1. First check: `python -c "import pdf2md"` -- if ImportError, ask user to run `pip install pdf2md` or `pip install /Users/tmayassi/projects/pdf2md`

2. If the argument is "benchmark", run the benchmark suite:

```python
import pdf2md
# pdf2md benchmark          — run on fast tier
# pdf2md benchmark --compare — compare all tiers
```

For the Nature quality harness, use `uv run python autoresearch/loop.py --agent codex --iterations 1`.
The current fast-tier output scores 100.0% weighted, with every weighted dimension at 100% except body coherence at 99.8%.

3. Parse arguments:
   - First arg: file path or URL (required)
   - --deep or --standard or --fast: tier (default: auto)
   - --figures skip|caption|describe|extract: figure handling (default: caption)
   - --provider <provider/model>: VLM provider override
   - --figures-json <path>: save the lightweight figure index sidecar

4. Run conversion:

```python
import pdf2md

# Parse tier from arguments (default: "auto")
tier = "auto"
figures = None
provider = None

# Extract flags from args
# --deep / --standard / --fast -> tier
# --figures <mode> -> figures
# --provider <string> -> provider

doc = pdf2md.convert(source, tier=tier, figures=figures, provider=provider)
```

5. Output to user:
   - Print the full markdown content
   - Print a summary line: "Converted N pages (engine: {engine}, tier: {tier}, {time}ms, {confidence}% confidence)"
   - If confidence < 70% on any page, flag those pages with a warning

6. Structured data access (if the user asks for it):
   - `doc.metadata.title` -- extracted title
   - `doc.metadata.authors` -- author list
   - `doc.metadata.doi` -- DOI if found
   - `doc.sections` -- list of Section(level, title, content, page)
   - `doc.tables` -- list of Table(id, markdown, headers, rows, confidence)
   - `doc.figures` -- list of Figure(id, caption, description, image_base64)
   - `doc.figure_index` -- lightweight FigureIndexEntry records for downstream figure querying; save with `doc.save_figure_index("paper.figures.json")`
   - Panel references: `from pdf2md.enhancers.captions import extract_panel_references; refs = extract_panel_references(doc.markdown)` -- returns list of dict(fig_num, panels, context)
   - `doc.equations` -- list of Equation(id, latex, inline, page)
   - `doc.bibliography` -- list of Reference(id, authors, title, journal, year, doi)

## Example Session

User: /pdf paper.pdf --deep

Assistant runs:

```python
import pdf2md

doc = pdf2md.convert("paper.pdf", tier="deep")
print(doc.markdown)
print(f"\n---\nConverted {doc.metadata.pages} pages (engine: {doc.engine_used}, tier: {doc.tier_used}, {doc.processing_time_ms}ms, {doc.confidence:.0%} confidence)")
print(f"  {len(doc.sections)} sections, {len(doc.tables)} tables, {len(doc.equations)} equations, {len(doc.figures)} figures")

# Show figures with captions and VLM descriptions
for fig in doc.figures:
    line = f"  {fig.id}: {fig.caption or '(no caption)'}"
    if fig.description:
        line += f" — {fig.description[:80]}..."
    print(line)

# Flag low-confidence pages
for i, score in enumerate(doc.page_confidences):
    if score < 0.7:
        print(f"  Warning: page {i+1} has low confidence ({score:.0%})")
```

## Error Handling

- If the file does not exist, report the error clearly
- If no VLM provider is configured and tier is standard/deep, fall back to fast tier and note this
- If conversion fails, show the error and suggest checking `pdf2md info` for engine status
