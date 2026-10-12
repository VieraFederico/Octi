"""Collect the Table context of an extracted Table (spec 01 FR-123 … FR-126; D-058, D-080).

Deterministic, no LLM. The context is chosen by position and font from PyMuPDF's text blocks:
1. A block can count for a Table only if it lies outside every table box, is not running text
   (repeated on more than half of the pages, in PDFs of at least 3 pages), is not a bare page
   number, and overlaps the Table horizontally by at least half the width of the narrower of the
   two (FR-124 as amended by S01-D-011: a full-width paragraph over a narrow table counts; text in
   the other column of a two-column page never does).
2. Around the Table's box, the counting blocks are listed nearest first, above and below, up to
   the next other table ("just above" = nothing in between).
3. Each field takes its block by role: caption, paragraph, footnotes, heading (FR-123); a
   multi-page Table reads above its first part and below its last part (FR-125).
4. The fields are cut to the size limits (FR-126).
"""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, replace

import pymupdf

from agents.ingestion.pdf.document import is_repeated
from agents.ingestion.schemas import Box, ExtractedTable, TableContext

# Code constants (spec 01 §7), not configuration.
MAX_PARAGRAPH_CHARS = 600  # `before` and `after`
MAX_CONTEXT_CHARS = 2000  # the five fields together
MAX_CAPTION_FALLBACK_LINES = 2
MAX_HEADING_WORDS = 12
LARGER_FONT = 0.5  # points above the page's most common size that make a line "larger"
EDGE_TOLERANCE = 2.0  # points: a block touching the table's edge is still above / below it

CAPTION = re.compile(r"(Table|Tabla|Cuadro)\s+\d+", re.IGNORECASE)
FOOTNOTE = re.compile(r"(\(\w{1,3}\)|\*+|[a-z0-9]\)|(Note|Nota|Source|Fuente):)", re.IGNORECASE)
PAGE_NUMBER = re.compile(r"[-–—\s]*\d{1,4}[-–—\s]*")


@dataclass(frozen=True)
class _Block:
    """One PyMuPDF text block, reduced to what the rules need."""

    page: int  # 1-based
    bbox: Box
    text: str  # whitespace and line breaks collapsed to single spaces
    lines: int
    heading_like: bool  # bold, or larger than the page's most common font size


def collect_context(doc: pymupdf.Document, table: ExtractedTable) -> TableContext:
    """The five-field Table context of `table`, each field `""` when not found (FR-123 … FR-126)."""
    layout = _Layout(doc)
    first_page, first_box = table.parts[0]
    last_page, last_box = table.parts[-1]
    above = layout.neighbours(first_page, first_box, above=True)
    below_first = layout.neighbours(first_page, first_box, above=False)
    below = layout.neighbours(last_page, last_box, above=False)

    caption = _caption(above, below_first)
    before = next((block for block in above if block is not caption), None)
    if before is not None and _is_heading(before):
        before = None

    rest = [block for block in below if block is not caption]
    footnotes: list[_Block] = []
    while rest and FOOTNOTE.match(rest[0].text):
        footnotes.append(rest.pop(0))
    after = rest[0] if rest and not _is_heading(rest[0]) else None

    context = TableContext(
        section=layout.section(first_page, first_box),
        caption=caption.text if caption else "",
        before=before.text[:MAX_PARAGRAPH_CHARS] if before else "",
        after=after.text[:MAX_PARAGRAPH_CHARS] if after else "",
        footnotes="\n".join(block.text for block in footnotes),
    )
    return _fit(context)


def _caption(above: list[_Block], below: list[_Block]) -> _Block | None:
    """`Table N` just above, else just below, else a block of at most 2 lines directly above that is
    not a heading (a heading is the section, not the caption)."""
    if above and CAPTION.match(above[0].text):
        return above[0]
    if below and CAPTION.match(below[0].text):
        return below[0]
    if above and above[0].lines <= MAX_CAPTION_FALLBACK_LINES and not _is_heading(above[0]):
        return above[0]
    return None


def _is_heading(block: _Block) -> bool:
    """At most 12 words, bold or larger than the page's usual text, and not a caption (FR-123)."""
    return block.heading_like and len(block.text.split()) <= MAX_HEADING_WORDS and not CAPTION.match(block.text)


def _fit(context: TableContext) -> TableContext:
    """Shorten `before`, then `after`, then `footnotes` until the total is at most 2,000 (FR-126)."""
    for name in ("before", "after", "footnotes"):
        excess = sum(len(value) for value in vars(context).values()) - MAX_CONTEXT_CHARS
        if excess <= 0:
            break
        value = getattr(context, name)
        context = replace(context, **{name: value[: max(0, len(value) - excess)]})
    return context


class _Layout:
    """The counting text blocks and the table boxes of each page, read once per call."""

    def __init__(self, doc: pymupdf.Document) -> None:
        self.doc = doc
        self.tables: dict[int, list[Box]] = {}
        self.blocks: dict[int, list[_Block]] = {}
        pages_by_text: dict[str, set[int]] = defaultdict(set)
        for page in doc:
            number = page.number + 1
            self.tables[number] = [tuple(found.bbox) for found in page.find_tables().tables]
            self.blocks[number] = [b for b in _text_blocks(page) if not self._inside_a_table(b)]
            for block in self.blocks[number]:
                pages_by_text[block.text].add(number)
        self.running = {text for text, pages in pages_by_text.items() if is_repeated(len(pages), doc.page_count)}

    def _inside_a_table(self, block: _Block) -> bool:
        x = (block.bbox[0] + block.bbox[2]) / 2
        y = (block.bbox[1] + block.bbox[3]) / 2
        return any(box[0] <= x <= box[2] and box[1] <= y <= box[3] for box in self.tables[block.page])

    def counting(self, page: int, box: Box) -> list[_Block]:
        """The page's blocks that may be context for a Table in `box` (FR-124)."""
        return [
            block
            for block in self.blocks[page]
            if block.text not in self.running
            and not PAGE_NUMBER.fullmatch(block.text)
            and _overlap(block.bbox, box) >= min(_width(block.bbox), _width(box)) / 2
        ]

    def neighbours(self, page: int, box: Box, *, above: bool) -> list[_Block]:
        """The counting blocks above (or below) `box`, nearest first, stopping at another table."""
        others = [t for t in self.tables[page] if t != box and _overlap(t, box) > 0]
        if above:
            limit = max((t[3] for t in others if t[3] <= box[1] + EDGE_TOLERANCE), default=float("-inf"))
            found = [b for b in self.counting(page, box) if b.bbox[3] <= box[1] + EDGE_TOLERANCE and b.bbox[1] >= limit]
            return sorted(found, key=lambda b: -b.bbox[3])
        limit = min((t[1] for t in others if t[1] >= box[3] - EDGE_TOLERANCE), default=float("inf"))
        found = [b for b in self.counting(page, box) if b.bbox[1] >= box[3] - EDGE_TOLERANCE and b.bbox[3] <= limit]
        return sorted(found, key=lambda b: b.bbox[1])

    def section(self, page: int, box: Box) -> str:
        """The nearest heading above `box`, then on earlier pages from the bottom up (FR-123)."""
        candidates = sorted(
            (b for b in self.counting(page, box) if b.bbox[3] <= box[1] + EDGE_TOLERANCE), key=lambda b: -b.bbox[3]
        )
        for earlier in range(page - 1, 0, -1):
            candidates += sorted(self.counting(earlier, box), key=lambda b: -b.bbox[3])
        return next((block.text for block in candidates if _is_heading(block)), "")


def _text_blocks(page: pymupdf.Page) -> list[_Block]:
    """The page's text blocks with their collapsed text, line count and heading look.

    MuPDF can put lines of two columns that sit at the same height into one block, so each block
    is first split into groups of lines that overlap horizontally (`_column_groups`).
    """
    # Without TEXT_PRESERVE_LIGATURES, "ﬁ" comes back as "fi" (table cells already do).
    flags = pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_LIGATURES
    raw = [block for block in page.get_text("dict", flags=flags)["blocks"] if block["type"] == 0]
    sizes: Counter[float] = Counter()
    for block in raw:
        for line in block["lines"]:
            for span in line["spans"]:
                sizes[round(span["size"], 1)] += len(span["text"].strip())
    common = sizes.most_common(1)[0][0] if sizes else 0.0
    blocks = []
    for block in raw:
        for lines in _column_groups(block["lines"]):
            spans = [span for line in lines for span in line["spans"] if span["text"].strip()]
            if not spans:
                continue
            text = " ".join(" ".join(span["text"] for line in lines for span in line["spans"]).split())
            bbox = (
                min(line["bbox"][0] for line in lines),
                min(line["bbox"][1] for line in lines),
                max(line["bbox"][2] for line in lines),
                max(line["bbox"][3] for line in lines),
            )
            bold = all(span["flags"] & pymupdf.TEXT_FONT_BOLD for span in spans)
            larger = max(span["size"] for span in spans) > common + LARGER_FONT
            blocks.append(_Block(page.number + 1, bbox, text, len(lines), bold or larger))
    return blocks


def _column_groups(lines: list[dict]) -> list[list[dict]]:
    """Split a block's lines into groups whose horizontal extents overlap, keeping line order."""
    groups: list[list[dict]] = []
    for line in lines:
        home = next((group for group in groups if any(_overlap(line["bbox"], other["bbox"]) > 0 for other in group)), None)
        if home is None:
            groups.append([line])
        else:
            home.append(line)
    return groups


def _width(box: Box) -> float:
    return box[2] - box[0]


def _overlap(a: Box, b: Box) -> float:
    """How far two boxes overlap horizontally, in points."""
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
