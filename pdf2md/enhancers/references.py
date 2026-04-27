"""Bibliography parser.

Locates the References / Bibliography section of a converted markdown
document, splits it into entries, and parses each entry into a
:class:`Reference`. Three citation styles are handled (Vancouver/AMA,
Nature/Cell, APA) plus a DOI/URL fallback that runs on every entry so a
recognisable identifier is always extracted when present.

Confidence scoring rewards each parsed field; the caller can route
low-confidence entries (``confidence < 0.5``) to a VLM if one is available.
The parser itself never makes network calls and never raises — missing
fields stay ``None`` / empty so downstream consumers can decide how to
handle partial parses.

Reference IDs are emitted as ``ref-N`` so they line up with the anchors
already injected by ``cross_references.add_cross_references``.
"""

from __future__ import annotations

import re

from pdf2md.document import Reference

# --- Section locators ----------------------------------------------------

_REFERENCES_HEADING_RE = re.compile(
    r"^\s*#{1,4}\s+(References|Bibliography)\s*$", re.IGNORECASE
)
_ANY_HEADING_RE = re.compile(r"^\s*#{1,4}\s+\S")

# Numbered entry openers. Match the variants we have seen in journal exports
# and prefer the bracketed form when both regexes would match (e.g. "[12]
# Smith J. ..." should not also count as the "12. Smith" form).
_ENTRY_BRACKET_RE = re.compile(r"^\s*\[(\d+)\]\s+(\S.*)$")
_ENTRY_DOTTED_RE = re.compile(r"^\s*(\d+)\.\s+(\S.*)$")
_ANCHOR_PREFIX_RE = re.compile(r'^<a\s+id="ref-\d+"></a>')
# Mid-line opener pattern. Two-column journal layouts can splice the
# left-column reference and the right-column reference onto one physical
# line; this regex finds the second opener so we can split it back out.
# Requires a capitalised surname (with comma or initial) right after the
# number to avoid matching "Fig. 3. The transformer" or "version 2. Update".
_INLINE_OPENER_RE = re.compile(
    r"\s(?P<num>\d{1,3})\.\s+(?=[A-Z][a-zA-Z'\-]+(?:,\s*[A-Z]\.|\s+et\s+al\.))"
)
# Author-year entry opener. Cell-press / many older Elsevier journals use an
# alphabetical, un-numbered reference list where each entry begins with a
# capitalised surname followed by a comma and at least one initial+period.
# We allow tight (``Smith,J.K.,``) and loose (``Smith, J.K.,``) spacing
# because the text-flattening step routinely loses inter-token whitespace
# when reflowing two-column journal layouts.
_AUTHOR_YEAR_OPENER_RE = re.compile(
    r"^\s*[A-Z][a-zA-Z'À-ſ\-]+,\s*[A-Z]\.(?:[A-Z]\.)?(?:,|\s+(?:and|&))"
)

# --- Field extractors (reused across styles) -----------------------------

_DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s,;<>\"\]]+)", re.IGNORECASE)
_URL_RE = re.compile(r"https?://[^\s,;<>()\[\]\"]+")
_YEAR_RE = re.compile(r"\b(19|20)\d{2}[a-z]?\b")
# A volume/page tail like "45, 100-110" or "45(2):100-110" or "45:100-10".
_VOLUME_PAGES_RE = re.compile(
    r"(?P<vol>\d+)\s*(?:\((?P<issue>[^)]+)\))?\s*[,:]\s*"
    r"(?P<pages>[A-Za-z]?\d+(?:[-–][A-Za-z]?\d+)?)"
)


# --- Public entry point --------------------------------------------------


def parse_references(markdown: str) -> list[Reference]:
    """Extract structured references from a markdown document.

    Returns an empty list when no ``## References`` (or ``Bibliography``)
    heading exists, when the section is empty, or when no entry openers can
    be found. The function is total: it never raises on malformed input.
    """
    if not markdown:
        return []

    section = _extract_references_section(markdown)
    if not section:
        return []

    entries = _split_entries(section)
    return [_parse_entry(num, raw) for num, raw in entries]


# --- Section extraction --------------------------------------------------


def _extract_references_section(markdown: str) -> str:
    """Return the body text of the References / Bibliography section.

    If multiple References headings exist (common when a paper has both
    "References" for the main text and "References" inside the Methods),
    the *last* one is used — that is the primary bibliography for the paper.
    The section spans from that heading to the next top-level heading or
    end-of-document, whichever comes first.

    If no explicit heading is present (Nature, Science, and many older
    journals omit it), fall back to detecting a dense run of consecutive
    numbered entries near the end of the document.
    """
    lines = markdown.split("\n")
    last_heading_idx: int | None = None
    for idx, line in enumerate(lines):
        if _REFERENCES_HEADING_RE.match(line):
            last_heading_idx = idx

    if last_heading_idx is not None:
        body: list[str] = []
        for line in lines[last_heading_idx + 1:]:
            if _ANY_HEADING_RE.match(line) and not _REFERENCES_HEADING_RE.match(line):
                break
            body.append(line)
        return "\n".join(body).strip()

    return _detect_implicit_reference_block(lines)


def _detect_implicit_reference_block(lines: list[str]) -> str:
    """Locate a bibliography block when no ``## References`` heading exists.

    Walks the document line-by-line tracking runs of entry openers (both
    numbered and author-year style). When a run reaches
    :data:`_IMPLICIT_RUN_THRESHOLD` we lock the start of the bibliography
    to the first opener in that run; the block then extends to end of
    document. The run itself doesn't need to be contiguous — interleaved
    continuation lines (long titles, page breaks) and short intervening
    text fragments are common in real exports.
    """
    candidate_start: int | None = None
    seen_count = 0

    for idx, line in enumerate(lines):
        if (
            _ENTRY_BRACKET_RE.match(line)
            or _ENTRY_DOTTED_RE.match(line)
            or _AUTHOR_YEAR_OPENER_RE.match(line)
        ):
            if candidate_start is None:
                candidate_start = idx
            seen_count += 1
        # Reset only on hard structural breaks. Short non-matching prose is
        # common between entries (figure captions, page footers, multi-line
        # titles), so we tolerate it.
        elif _ANY_HEADING_RE.match(line):
            candidate_start = None
            seen_count = 0

        if seen_count >= _IMPLICIT_RUN_THRESHOLD and candidate_start is not None:
            return "\n".join(lines[candidate_start:]).strip()

    return ""


# Many numbered entries in a row are unlikely to be anything but a
# bibliography. Ten is conservative enough to avoid false positives on
# numbered list bodies that aren't references.
_IMPLICIT_RUN_THRESHOLD = 10


def _split_entries(section: str) -> list[tuple[int, str]]:
    """Group section lines into ``(number, raw_text)`` tuples.

    Entries can span multiple physical lines (DOIs, long titles, etc.), so
    we collect lines under the most recent opener until the next opener or
    blank-only block appears. Cross-reference anchors (``<a id="ref-N">``)
    that PR #13 may have prefixed are stripped before number detection.

    A secondary scan looks inside each entry's text for a mid-line opener
    pattern — common when a two-column journal layout splices the
    left-column entry's continuation with the right-column entry's
    opener onto one physical line. Whatever comes after that opener is
    split off into its own entry.

    When the section has no numbered openers at all, fall back to the
    author-year splitter (Cell-press, Trends, older Elsevier journals
    that emit alphabetised, un-numbered reference lists).
    """
    entries: list[tuple[int, list[str]]] = []
    for raw_line in section.split("\n"):
        line = _ANCHOR_PREFIX_RE.sub("", raw_line, count=1)
        bracket = _ENTRY_BRACKET_RE.match(line)
        dotted = _ENTRY_DOTTED_RE.match(line) if not bracket else None
        if bracket:
            entries.append((int(bracket.group(1)), [bracket.group(2)]))
        elif dotted:
            entries.append((int(dotted.group(1)), [dotted.group(2)]))
        elif entries and line.strip():
            entries[-1][1].append(line.strip())

    if not entries:
        return _split_author_year_entries(section)

    expanded: list[tuple[int, str]] = []
    for num, parts in entries:
        text = " ".join(parts).strip()
        for split_num, split_text in _split_spliced_entry(num, text):
            expanded.append((split_num, split_text))
    return expanded


def _split_author_year_entries(section: str) -> list[tuple[int, str]]:
    """Split an author-year reference section into ``(seq, raw)`` tuples.

    Author-year reference lists carry no inherent entry number, so we
    assign sequential ``1..N`` ids to keep downstream anchor wiring stable.
    The opener regex alone is not enough — long author lists wrap onto a
    second physical line that also begins with a ``Surname, X.`` token
    and would erroneously trigger a new entry. We treat the previous
    entry as still-open until it has captured a ``(YYYY)`` marker, which
    reliably signals end-of-authors.
    """
    entries: list[list[str]] = []
    for raw_line in section.split("\n"):
        line = _ANCHOR_PREFIX_RE.sub("", raw_line, count=1).strip()
        if not line:
            continue
        if _AUTHOR_YEAR_OPENER_RE.match(line) and (
            not entries or _entry_has_year(entries[-1])
        ):
            entries.append([line])
        elif entries:
            entries[-1].append(line)

    return [(idx + 1, " ".join(parts).strip()) for idx, parts in enumerate(entries)]


def _entry_has_year(parts: list[str]) -> bool:
    """Return True once the buffered entry has captured a ``(YYYY)`` marker."""
    return bool(_CELL_YEAR_MARKER_RE.search(" ".join(parts)))


def _split_spliced_entry(number: int, text: str) -> list[tuple[int, str]]:
    """Recover entries that share a physical line.

    Returns one or more ``(number, text)`` tuples. The leading entry keeps
    the original number; trailing entries take the number from the inline
    opener that introduced them.
    """
    pieces: list[tuple[int, str]] = []
    cursor = 0
    current_num = number
    for match in _INLINE_OPENER_RE.finditer(text):
        chunk = text[cursor : match.start()].strip()
        if chunk:
            pieces.append((current_num, chunk))
        current_num = int(match.group("num"))
        cursor = match.end()

    tail = text[cursor:].strip()
    if tail:
        pieces.append((current_num, tail))
    if not pieces:
        pieces.append((number, text))
    return pieces


# --- Per-entry parsing ---------------------------------------------------


def _parse_entry(number: int, raw: str) -> Reference:
    """Parse a single entry into a :class:`Reference`.

    Strategy: pull DOI, URL, and year out first since their regexes are
    style-agnostic, then dispatch to the most specific parser that fits the
    entry structure. Whatever the dispatch returns is merged with the
    style-agnostic fields and a confidence score is computed from how many
    real values we ended up with.
    """
    raw = raw.strip()
    ref_id = f"ref-{number}"

    doi = _extract_doi(raw)
    url = _extract_url(raw)
    year = _extract_year(raw)

    parsed = _dispatch_style(raw)

    ref = Reference(
        id=ref_id,
        raw=raw,
        authors=parsed.get("authors", []),
        title=parsed.get("title", ""),
        journal=parsed.get("journal"),
        year=year,
        volume=parsed.get("volume"),
        pages=parsed.get("pages"),
        doi=doi,
        url=url,
    )
    ref.confidence = _score_confidence(ref)
    return ref


def _dispatch_style(raw: str) -> dict[str, object]:
    """Pick the best style parser for ``raw`` and return its field dict.

    Detection cues:
      * Cell author-year: an opener with multiple ``Surname, X.,`` tokens
        followed somewhere by ``(YYYY).`` mid-entry. Both the squished
        (``Smith,J.,Jones,K.``) and loose variants are handled together.
      * APA: a year in parentheses immediately followed by ``. `` and the
        title — the style hangs the title off the year token with a
        sentence-style space.
      * Nature/Cell-numbered: a year in parentheses at end-of-entry
        (``(2023).`` as the final clause) with the journal-volume-pages
        comma form.
      * Vancouver/AMA fallback otherwise — periods separate
        authors/title/journal and ``year;vol(issue):pages`` follows.
    """
    # Nature style ends with ``(YYYY).`` — defer to it whenever the year
    # marker is the final clause, even if the opener also matches the
    # Cell author-year regex (Nature entries do start with ``Smith, J.``).
    if re.search(r"\(\d{4}[a-z]?\)\s*\.?\s*$", raw):
        return _parse_nature(raw)
    # Cell-press author-year reference lists routinely lose inter-token
    # whitespace and use the ``,? and`` connector (or no connector at all)
    # before the last author, while APA strictly uses ``, &``. Routing
    # Cell entries here lets us anchor on the ``vol, pages`` regex
    # rather than relying on APA's ``Title. Journal,`` separator that
    # the squished output destroys.
    if (
        _AUTHOR_YEAR_OPENER_RE.match(raw)
        and re.search(r"\(\d{4}[a-z]?\)", raw)
        and not re.search(r",\s*&\s*[A-Z]", raw)
    ):
        return _parse_cell_author_year(raw)
    if re.search(r"\(\d{4}[a-z]?\)\.\s+\S", raw):
        return _parse_apa(raw)
    return _parse_vancouver(raw)


# --- Style: Vancouver / AMA ---------------------------------------------
#
# Example: "Smith J, Jones K. Title of paper. Journal Name. 2023;45(2):100-110."


def _parse_vancouver(raw: str) -> dict[str, object]:
    """Parse the Vancouver/AMA period-separated layout.

    The format is brittle — punctuation drift in scanned PDFs eats periods
    and merges fields — so we collect what we can and let
    :func:`_score_confidence` decide if the parse is trustworthy.
    """
    chunks = _split_top_level(raw, separator=". ")
    if len(chunks) < 2:
        return {}

    authors = _split_authors_vancouver(chunks[0])
    title = chunks[1].rstrip(". ")

    # Find the chunk that contains "year;vol(issue):pages" — usually the last.
    journal = None
    volume = None
    pages = None
    if len(chunks) >= 4:
        journal = chunks[2].rstrip(". ")
        volume, pages = _extract_volume_pages(chunks[3])
    elif len(chunks) == 3:
        # journal and tail collapsed into one chunk: "Journal. 2023;45:100-10"
        tail = chunks[2]
        journal_match = re.match(r"^(.+?)\.\s*(?:\d{4}|\d+\s*[,:])", tail)
        if journal_match:
            journal = journal_match.group(1).strip()
            volume, pages = _extract_volume_pages(tail[journal_match.end():])
        else:
            journal = tail.rstrip(". ")

    return {
        "authors": authors,
        "title": title,
        "journal": journal,
        "volume": volume,
        "pages": pages,
    }


def _split_authors_vancouver(chunk: str) -> list[str]:
    """Split a Vancouver author block — comma-separated ``Smith J`` tokens."""
    parts = [a.strip() for a in chunk.split(",")]
    return [a for a in parts if a]


# --- Style: Nature / Cell ------------------------------------------------
#
# Example: "Smith, J. & Jones, K. Title of paper. J. Name 45, 100-110 (2023)."


# A single Nature/Cell author token: ``Surname, X.`` with optional extra
# initials. Matching the author *block* with this avoids the periods inside
# initials being confused with sentence boundaries.
_NATURE_AUTHOR_TOKEN = (
    r"[A-Z][A-Za-z'À-ſ\-]+,\s+[A-Z]\.(?:\s*-?\s*[A-Z]\.)*"
)
_NATURE_AUTHORS_RE = re.compile(
    rf"^(?P<block>{_NATURE_AUTHOR_TOKEN}"
    rf"(?:(?:,\s+|\s+(?:&|and)\s+){_NATURE_AUTHOR_TOKEN})*)"
)


def _parse_nature(raw: str) -> dict[str, object]:
    """Parse Nature/Cell-style entries that end with ``(YYYY)``.

    The author block uses ``,`` between successive entries and ``&`` (or
    ``and``) before the last author. The journal/volume/pages tail comes
    just before the year-in-parens marker. We match the author block
    explicitly because period-space is ambiguous with author initials —
    splitting blindly on ``". "`` shears ``Smith, J.`` in two.
    """
    year_marker = re.search(r"\(\d{4}[a-z]?\)\s*\.?\s*$", raw)
    body = raw[: year_marker.start()].rstrip(" .,") if year_marker else raw

    author_match = _NATURE_AUTHORS_RE.match(body)
    if not author_match:
        return {}

    authors = _split_authors_nature(author_match.group("block"))
    rest = body[author_match.end():].lstrip(" .")

    # ``rest`` looks like ``Title. Journal vol, pages``. The volume/pages
    # tail is the most distinctive token — anchor on it and split the
    # title/journal off whatever sits in front.
    vp_match = _VOLUME_PAGES_RE.search(rest)
    title = ""
    journal = None
    volume = None
    pages = None

    if vp_match:
        head = rest[: vp_match.start()].rstrip(", .")
        # ``head`` is ``Title. Journal`` — split on the LAST ``". "`` so
        # multi-clause titles stay intact.
        split_at = head.rfind(". ")
        if split_at >= 0:
            title = head[:split_at].strip()
            journal = head[split_at + 2:].strip().rstrip(", .")
        else:
            title = head.strip()
        volume = vp_match.group("vol")
        pages = vp_match.group("pages")
    else:
        title = rest.rstrip(". ")

    return {
        "authors": authors,
        "title": title,
        "journal": journal,
        "volume": volume,
        "pages": pages,
    }


def _split_authors_nature(block: str) -> list[str]:
    """Pull individual ``Surname, X.`` tokens out of a Nature author block."""
    return [m.group(0).rstrip(",;") for m in re.finditer(_NATURE_AUTHOR_TOKEN, block)]


def _clean_author(text: str) -> str:
    return text.strip().strip(".,;")


# --- Style: Cell author-year --------------------------------------------
#
# Example (loose):
#   "Smith, J., Jones, K., and Lee, S. (2023). Title of paper. Journal 45,
#   100-110."
#
# Example (squished — common after column-aware reflow):
#   "Smith,J.,Jones,K.,andLee,S.(2023).Titleofpaper.Journal45,100-110."
#
# Cell-press, Trends, and many older Elsevier journals use this style with
# an alphabetised, un-numbered reference list. The reflow step regularly
# loses inter-token whitespace; we anchor on the ``(YYYY)`` marker rather
# than relying on consistent spacing.


# Squished or loose Cell author token: ``Surname,X.[Y.]``. The tail token
# matcher allows zero, one, or two initial periods so multi-initial authors
# like ``Smith, J.K.`` round-trip.
_CELL_AUTHOR_TOKEN = (
    r"[A-Z][a-zA-Z'À-ſ\-]+,\s*[A-Z]\.(?:\s*-?\s*[A-Z]\.)*"
)
_CELL_AUTHOR_TOKEN_RE = re.compile(_CELL_AUTHOR_TOKEN)
_CELL_YEAR_MARKER_RE = re.compile(r"\((\d{4}[a-z]?)\)\.?\s*")


def _parse_cell_author_year(raw: str) -> dict[str, object]:
    """Parse a Cell-style ``Authors. (YYYY). Title. Journal vol, pages.`` entry.

    Anchors on the year-in-parens marker because Cell exports lose
    inter-token whitespace inconsistently and the period that normally
    separates title and journal is unreliable. The volume/pages tail is
    distinctive and gives us the right edge of the title.
    """
    year_match = _CELL_YEAR_MARKER_RE.search(raw)
    if not year_match:
        return {}

    # Trim only whitespace and trailing commas — never the period, since
    # the last author's initial ends with one (``..., Decaluwe, H.``)
    # and rstrip-ing periods would shear the final initial off.
    authors_chunk = raw[: year_match.start()].rstrip(" ,")
    tail = raw[year_match.end():].lstrip(" .")

    authors = _split_authors_cell(authors_chunk)

    # ``tail`` is ``Title.Journal vol, pages.`` (squished) or
    # ``Title. Journal vol, pages.`` (loose). Anchor on the volume/pages
    # tail; whatever sits in front is title + journal.
    vp_match = _VOLUME_PAGES_RE.search(tail)
    title = ""
    journal: str | None = None
    volume: str | None = None
    pages: str | None = None

    if vp_match:
        head = tail[: vp_match.start()].rstrip(", .")
        # Journal name precedes the volume number with a single space —
        # find the LAST whitespace before the volume so multi-word journal
        # abbreviations like ``Nat. Protoc.`` stay intact.
        space_at = head.rfind(" ")
        if space_at >= 0:
            journal_candidate = head[space_at + 1:].strip(", .")
            title_head = head[:space_at].rstrip(", .")
            # Split title from journal: title ends with the LAST ``. ``
            # before the journal token, but in squished output the period
            # may have no trailing space. Try both forms.
            split_at = title_head.rfind(". ")
            if split_at < 0:
                # Squished form: walk back to find ``.<UpperCase>`` boundary
                # adjacent to the journal candidate.
                squished_split = re.search(r"\.(?=[A-Z][a-zA-Z]*\.?$)", title_head)
                split_at = squished_split.start() if squished_split else -1
                offset = 1
            else:
                offset = 2
            if split_at >= 0:
                title = title_head[:split_at].strip()
                inline_journal = title_head[split_at + offset:].strip(", .")
                journal = (
                    f"{inline_journal} {journal_candidate}".strip(", .")
                    if inline_journal
                    else journal_candidate
                )
            else:
                title = title_head.strip()
                journal = journal_candidate
        else:
            title = head.strip()
        volume = vp_match.group("vol")
        pages = vp_match.group("pages")
    else:
        # No volume/pages tail — keep everything after the year as the title.
        title = tail.rstrip(". ")

    return {
        "authors": authors,
        "title": title,
        "journal": journal,
        "volume": volume,
        "pages": pages,
    }


def _split_authors_cell(chunk: str) -> list[str]:
    """Pull individual ``Surname, X.`` tokens out of a Cell author block.

    Both squished (``Smith,J.,Jones,K.``) and loose (``Smith, J., Jones, K.``)
    variants surface; the token regex tolerates either form. Trailing
    ``etal``/``et al.`` markers are dropped.
    """
    return [
        re.sub(r",\s*", ", ", m.group(0)).strip(" ,;")
        for m in _CELL_AUTHOR_TOKEN_RE.finditer(chunk)
    ]


# --- Style: APA ----------------------------------------------------------
#
# Example: "Smith, J., & Jones, K. (2023). Title of paper. Journal, 45(2), 100-110."


def _parse_apa(raw: str) -> dict[str, object]:
    """Parse APA-style entries with the ``(YYYY).`` author/title separator."""
    sep = re.search(r"\((\d{4}[a-z]?)\)\.\s*", raw)
    if not sep:
        return {}

    authors_chunk = raw[: sep.start()].rstrip(" .,")
    rest = raw[sep.end():]

    authors = _split_authors_apa(authors_chunk)

    # rest = "Title. Journal, vol(issue), pages."
    title_match = re.match(r"^(.+?)\.\s+(.+)$", rest)
    if not title_match:
        return {"authors": authors, "title": rest.rstrip(". ")}

    title = title_match.group(1).strip()
    tail = title_match.group(2)

    vp_match = _VOLUME_PAGES_RE.search(tail)
    if vp_match:
        journal = tail[: vp_match.start()].rstrip(", .")
        volume = vp_match.group("vol")
        pages = vp_match.group("pages")
    else:
        journal = tail.rstrip(". ")
        volume = None
        pages = None

    return {
        "authors": authors,
        "title": title,
        "journal": journal,
        "volume": volume,
        "pages": pages,
    }


def _split_authors_apa(chunk: str) -> list[str]:
    """Split an APA author block — ``,`` separated, sometimes with ``&``."""
    normalised = re.sub(r",\s*&\s*", ", ", chunk)
    # Author tokens look like "Smith, J." — pair every other comma-split token.
    raw_parts = [p.strip() for p in normalised.split(",")]
    authors: list[str] = []
    i = 0
    while i < len(raw_parts):
        # Pair "Smith" with the next "J." token, if present.
        surname = raw_parts[i].strip(".,; ")
        if not surname:
            i += 1
            continue
        if i + 1 < len(raw_parts) and re.match(r"^[A-Z]\.?(?:\s*[A-Z]\.?)*$", raw_parts[i + 1].strip(".,; ")):
            authors.append(f"{surname}, {raw_parts[i + 1].strip().rstrip(',')}")
            i += 2
        else:
            authors.append(surname)
            i += 1
    return authors


# --- Field extraction helpers --------------------------------------------


def _extract_doi(text: str) -> str | None:
    match = _DOI_RE.search(text)
    if not match:
        return None
    # Trailing punctuation (sentence period, list comma) attaches to the DOI
    # but is never part of one — strip it. Note that DOIs themselves may
    # legitimately contain periods, so we only strip from the right.
    return match.group(1).rstrip(".,;)")


def _extract_url(text: str) -> str | None:
    match = _URL_RE.search(text)
    if not match:
        return None
    return match.group(0).rstrip(".,;)")


def _extract_year(text: str) -> str | None:
    match = _YEAR_RE.search(text)
    return match.group(0) if match else None


def _extract_volume_pages(text: str) -> tuple[str | None, str | None]:
    match = _VOLUME_PAGES_RE.search(text)
    if not match:
        return None, None
    return match.group("vol"), match.group("pages")


def _split_top_level(text: str, *, separator: str) -> list[str]:
    """Split on ``separator`` while ignoring matches inside parentheses.

    Citation entries have parens around years, locations, and editor notes
    — splitting blindly on ``". "`` shreds those. We track depth so the
    splitter only fires when we are at parenthesis depth 0.
    """
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    sep_len = len(separator)
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if depth == 0 and text[i : i + sep_len] == separator:
            parts.append("".join(buf).strip())
            buf = []
            i += sep_len
            continue
        buf.append(ch)
        i += 1
    if buf:
        parts.append("".join(buf).strip())
    return [p for p in parts if p]


# --- Confidence scoring --------------------------------------------------


def _score_confidence(ref: Reference) -> float:
    """Combine field presence into a 0-1 confidence score.

    Title and authors are the most expensive fields to recover from raw
    text, so they carry the most weight. DOI is worth less per-bit because
    it is recoverable purely by regex on the raw text.
    """
    score = 0.0
    if ref.authors:
        score += 0.25
    if ref.title:
        score += 0.25
    if ref.journal:
        score += 0.15
    if ref.year:
        score += 0.15
    if ref.doi:
        score += 0.20
    return min(1.0, score)
