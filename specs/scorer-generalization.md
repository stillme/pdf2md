# Spec: Generalize the benchmark scorer

Status: Draft
Owner: —
Branch: `claude/review-progress-specs-UGiug`
Related: PRs #1–#4 (all merged into `main`)

## Problem

`autoresearch/scorer.py` hardcodes every expected value against a single Nature
paper (Mayassi et al., `s41586-024-08216-z`): title, DOI, author surnames,
figure count, caption prefixes, headings, compound words, key phrases,
legend-leak terms, and superscript patterns. PRs #1–#4 drove the weighted
total to 100% on that paper, but the feedback loop only "knows" one fixture:
every improvement is measured against the same document.

Two consequences:

1. **Overfitting.** Changes that help Nature may silently regress other
   layouts. We have no signal for arXiv ML papers, math papers, or
   technical reports even though `pdf2md/benchmarks/runner.py` already
   downloads them.
2. **Reproducibility friction.** `BENCHMARK_PAPERS` carries hardcoded
   `/Users/tmayassi/Downloads/...` paths (`runner.py:47,56`), so the
   benchmark cannot run in CI, web sessions, or on another developer's
   machine without edits.

The benchmark runner collects pages, sections, tables, and confidence for
every paper — but quality scoring only fires for the Nature fixture, and
only because its constants are baked into `scorer.py`.

## Goals

- Move per-paper ground truth out of `scorer.py` into a fixture registry.
- Make `score_output(markdown, truth)` paper-agnostic so any paper with a
  fixture can be scored.
- Run quality scoring across the full `BENCHMARK_PAPERS` list and report
  per-paper + aggregate scores.
- Remove user-specific absolute paths from the benchmark registry.
- Preserve Nature's current 100.0% weighted total (no regression during
  migration).

## Non-goals

- Rewriting `pdf2md/confidence.py` or the extraction pipeline.
- Changing tier semantics (`fast` / `standard` / `deep`).
- Overhauling the verifier loop (`pdf2md/verifier.py`) — tracked separately.
- Adding LLM-based scoring. The scorer stays deterministic and pattern-based.

## Design

### Fixture schema

Each scorable paper carries a JSON fixture. JSON (not YAML) keeps the
dependency surface empty and matches the figure-index sidecar convention
from PR #3.

```
autoresearch/fixtures/
  _common.json                  # shared patterns across all papers
  nature-gut-adaptation.json    # one fixture per paper
  attention-is-all-you-need.json
  bert.json
  ...
```

Per-paper fixture (example, abbreviated):

```json
{
  "id": "nature-gut-adaptation",
  "source": {
    "url": "",
    "local_filename": "s41586-024-08216-z.pdf"
  },
  "metadata": {
    "title": "Spatially restricted immune and microbiota-driven adaptation of the gut",
    "doi": "10.1038/s41586-024-08216-z",
    "authors": ["Mayassi", "Li", "Segerstolpe", "Brown", "Weisberg",
                "Nakata", "Yano", "Herbst", "Artis", "Graham", "Xavier"]
  },
  "figures": {
    "expected_count": 15,
    "ideal_range": [10, 25],
    "per_overshoot_penalty": 0.03,
    "main_captions": ["Fig. 1", "Fig. 2", "Fig. 3", "Fig. 4", "Fig. 5"],
    "extended_captions": [
      "Extended Data Fig. 1", "Extended Data Fig. 2", "...",
      "Extended Data Fig. 10"
    ],
    "leak_terms": [
      "Short chain fatty acids", "Adenosine triphosphate",
      "Beta-lactam antibiotics"
    ]
  },
  "headings": [
    "Constructing the spatial transcriptome",
    "The intestinal landscape is robust",
    "Methods", "References"
  ],
  "compounds": {
    "expected": ["microbiota-driven", "region-enriched", "single-cell",
                 "co-housed", "immune-mediated"]
  },
  "key_phrases": [
    "spatial transcriptome", "murine intestine", "Visium",
    "goblet cells", "faecal microbiota transplant"
  ],
  "superscripts": {
    "expected_patterns": [
      "Mayassi<sup>\\d", "Li<sup>\\d", "Xavier<sup>\\d", "regions<sup>1"
    ]
  }
}
```

Common fixture (shared pattern library):

```json
{
  "legend_language": [
    "scale bar,", "representative of n =", "biological replicate",
    "error bars represent", "processed using imagej",
    "see next page for caption"
  ],
  "universal_bad_joins": [
    "singlecell", "singlemolecule", "multiomics"
  ],
  "false_positive_superscripts": [
    "fig<sup>", "tab<sup>", "eq<sup>"
  ]
}
```

Rationale for the split:
- Legend language is universal across biomedical figures; no paper needs
  its own copy.
- `universal_bad_joins` catches any paper producing malformed compounds
  regardless of ground truth. Paper-specific "good compounds" stay in the
  per-paper file because they depend on content.
- `false_positive_superscripts` are pipeline errors, not paper-specific.

### Scorer signature change

`score_output` gains a ground-truth argument. Each dimension function
takes only what it needs; the top-level caller threads the fixture
through.

```python
# autoresearch/scorer.py
@dataclass(frozen=True)
class GroundTruth:
    id: str
    metadata: MetadataTruth
    figures: FigureTruth
    headings: list[str]
    compounds_expected: list[str]
    key_phrases: list[str]
    superscripts_expected: list[str]

@dataclass(frozen=True)
class CommonPatterns:
    legend_language: list[str]
    universal_bad_joins: list[str]
    false_positive_superscripts: list[str]

def score_output(
    markdown: str,
    truth: GroundTruth,
    common: CommonPatterns,
) -> dict[str, float]: ...
```

`DIMENSIONS` and `WEIGHTS` remain; the module-level `EXPECTED_*` constants
are deleted.

### Fixture loader

```python
# autoresearch/fixtures.py
def load_ground_truth(paper_id: str) -> GroundTruth: ...
def load_common() -> CommonPatterns: ...
def list_fixtures() -> list[str]: ...
```

Loader reads from `autoresearch/fixtures/*.json`, validates required
fields, and returns frozen dataclasses. Fixtures without a corresponding
entry are skipped by the loop with a warning, not an error.

### Benchmark registry changes

Replace `path: "/Users/tmayassi/Downloads/..."` with:

```python
BENCHMARK_PAPERS = [
    {
        "id": "nature-gut-adaptation",
        "url": "",
        "local_filename": "s41586-024-08216-z.pdf",
        "fixture": "nature-gut-adaptation",
        "expected_pages": 41,
        "category": "nature-article",
    },
    ...
]
```

PDF resolution order in `_load_pdf`:

1. If `url` is set and reachable → download.
2. Else if `local_filename` set → look in `$PDF2MD_BENCHMARK_DIR` (default
   `~/pdf2md-benchmarks`).
3. Else skip with a clear message.

No absolute user paths anywhere in committed code.

### Runner + loop integration

`runner._convert_paper` learns to call the scorer when a fixture exists:

```python
if paper.get("fixture"):
    truth = load_ground_truth(paper["fixture"])
    scores = score_output(doc.markdown, truth, common)
    result.quality_scores = scores
```

`BenchmarkResult` gains `quality_scores: dict[str, float] | None`.
`print_summary` prints per-paper quality when present and an aggregate at
the bottom (mean + min weighted total across scored papers).

`autoresearch/loop.py` objective changes from
"improve Nature's weighted total" to "improve the min weighted total
across all scored fixtures" (configurable via `--objective mean|min`).
`min` punishes regressions; `mean` is smoother during early iterations.

### Migration plan

1. **Port Nature fixture first.** Move every `EXPECTED_*` constant from
   `scorer.py` into `autoresearch/fixtures/nature-gut-adaptation.json`
   and `_common.json`. Delete constants from `scorer.py` only after the
   new pipeline reproduces the old score.
2. **Golden test.** Add a test that runs the old hardcoded scorer vs the
   new ground-truth scorer on the current Nature markdown output and
   asserts identical per-dimension scores. Delete the old entry points
   once green.
3. **Add attention-is-all-you-need fixture.** Shortest, cleanest arXiv
   paper in the list; good second data point. Ground truth bootstraps
   from a manual review of the current `fast`-tier output.
4. **Add bert fixture.** Third data point for cross-paper signal.
5. **Wire loop objective** to `min` across the 3 fixtures. Re-run the
   autoresearch loop and confirm Nature does not regress below 99.9%.

Subsequent papers (GPT-4 technical report, math paper, Mistral) get
fixtures as we need them, but are not blockers for this spec.

## Open questions

- **Aggregate objective during iteration.** `min` punishes regressions
  but can oscillate on a noisy dimension; `mean` is stabler but hides a
  newly broken paper. Proposal: `min` with a configurable floor on
  Nature so it cannot regress below 99%.
- **Fixture authoring for new papers.** Manual the first time; worth a
  one-off `autoresearch bootstrap-fixture <paper>` helper that scaffolds
  a fixture from the current extraction output? Defer until we have
  more than 3.
- **Do the per-paper `expected_count` / `ideal_range` / `per_overshoot_penalty`
  belong in fixtures or stay hardcoded in `score_figure_count`?**
  Proposal: in fixtures, because figure counts differ substantially
  across paper types and the penalty curve matters.

## Success criteria

- `scorer.py` contains no paper-specific constants; all per-paper data
  loads from `autoresearch/fixtures/`.
- Nature weighted total ≥ 99.9% after migration (no regression).
- At least 2 additional papers (attention, bert) scored end-to-end.
- `pdf2md benchmark` runs with no hardcoded absolute paths; local PDFs
  resolve via `$PDF2MD_BENCHMARK_DIR`.
- `autoresearch/loop.py --objective min` iterates against the cross-paper
  floor rather than Nature alone.
- Existing 257 unit tests still pass; at least one new test asserts the
  fixture loader + scorer round-trip reproduces pre-migration Nature
  scores.

## Out of scope (tracked separately)

- Confidence scoring improvements for table-heavy and equation-heavy
  pages (`pdf2md/confidence.py`).
- Verifier loop reliability: error masking, patch application safety
  (`pdf2md/verifier.py`).
- Provider rate-limiting beyond Gemini's 4s sleep.
- Math correctness scoring for the dg-emi math paper.
