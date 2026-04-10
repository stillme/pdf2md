---
name: pdf
description: Convert a PDF file to clean, structured markdown using the pdf2md agentic parser. Handles text, tables, math, figures, and complex layouts. Three quality tiers (fast/standard/deep) with optional VLM verification.
---

Convert a PDF to markdown using pdf2md.

## Usage

/pdf <file_path_or_url> [options]

Examples:
- /pdf paper.pdf
- /pdf paper.pdf --deep
- /pdf paper.pdf --figures describe
- /pdf https://arxiv.org/pdf/2301.00001.pdf

## How It Works

1. Check if pdf2md is installed; if not, offer to install it
2. Run conversion with the specified options
3. Return the markdown directly into the conversation context
4. For deep tier, show confidence scores

## Implementation

When the user invokes /pdf:

1. First check: `python -c "import pdf2md"` -- if ImportError, ask user to run `pip install pdf2md` or `pip install /Users/tmayassi/projects/pdf2md`

2. Parse arguments:
   - First arg: file path or URL (required)
   - --deep or --standard or --fast: tier (default: auto)
   - --figures skip|caption|describe|extract: figure handling (default: caption)
   - --provider <provider/model>: VLM provider override

3. Run conversion:

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

4. Output to user:
   - Print the full markdown content
   - Print a summary line: "Converted N pages (engine: {engine}, tier: {tier}, {time}ms, {confidence}% confidence)"
   - If confidence < 70% on any page, flag those pages with a warning

5. Structured data access (if the user asks for it):
   - `doc.metadata.title` -- extracted title
   - `doc.metadata.authors` -- author list
   - `doc.metadata.doi` -- DOI if found
   - `doc.sections` -- list of Section(level, title, content, page)
   - `doc.tables` -- list of Table(id, markdown, headers, rows, confidence)
   - `doc.figures` -- list of Figure(id, caption, description)
   - `doc.bibliography` -- list of Reference(id, authors, title, journal, year, doi)

## Example Session

User: /pdf paper.pdf --deep

Assistant runs:

```python
import pdf2md

doc = pdf2md.convert("paper.pdf", tier="deep")
print(doc.markdown)
print(f"\n---\nConverted {doc.metadata.pages} pages (engine: {doc.engine_used}, tier: {doc.tier_used}, {doc.processing_time_ms}ms, {doc.confidence:.0%} confidence)")

# Flag low-confidence pages
for i, score in enumerate(doc.page_confidences):
    if score < 0.7:
        print(f"  Warning: page {i+1} has low confidence ({score:.0%})")
```

## Error Handling

- If the file does not exist, report the error clearly
- If no VLM provider is configured and tier is standard/deep, fall back to fast tier and note this
- If conversion fails, show the error and suggest checking `pdf2md info` for engine status
