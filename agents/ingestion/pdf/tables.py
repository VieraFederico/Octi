"""Find the Tables of a PDF and turn each into clean data (spec 01 FR-109 … FR-113 step 1, FR-119
table part, FR-122). Deterministic, no LLM.

Per page, PyMuPDF's `find_tables()` gives each table's cells (`None` = a position covered by a
merged cell), each cell's box and the table's box. This module then:
1. drops fake tables (FR-110) and flags unreadable ones (FR-119);
2. decides how many top rows are header rows (FR-113 step 1);
3. joins a table continued on the next page (FR-111, FR-112);
4. hands header rows and data rows to `cleaning.py` (flattening, number parsing).
"""

import hashlib
import logging
import re
from dataclasses import dataclass

import pymupdf

from agents.ingestion.pdf.cleaning import MISSING_VALUES, build_dataframe, clean_column, flatten_headers, row_headers
from agents.ingestion.schemas import Box, ExtractedTable

logger = logging.getLogger(__name__)

# Code constants (spec 01 §7), not configuration.
MAX_HEADER_ROWS = 3
YEAR_LABEL = re.compile(r"\d{4}")  # a year written as four plain digits …
YEAR_RANGE = range(1900, 2101)  # … from 1900 to 2100 counts as a label (FR-113 step 1)
MERGE_TOLERANCE = 0.5  # points: a cell wider than its column by more is a horizontal merge
REPLACEMENT_CHARACTER = "�"
UNREADABLE_SHARE = 0.25  # `�` in at least a quarter of the filled cells → unreadable (FR-119)


@dataclass
class _Part:
    """One table exactly as PyMuPDF found it on one page."""

    page: int  # 1-based
    position: int  # 1-based, top to bottom (FR-109)
    bbox: Box
    rows: list[list[str | None]]
    boxes: list[list[Box | None]]
    bold: list[bool]  # per row: every piece of text in the row is bold
    column_spans: list[tuple[float, float]]
    header_count: int = 0


def document_sha(data: bytes) -> str:
    """The full SHA-256 of the PDF bytes, in hex (D-048; also the Index record's `document_sha`)."""
    return hashlib.sha256(data).hexdigest()


def make_table_id(sha: str, page: int, position: int) -> str:
    """`<first 16 hex characters of the hash>-p<page>-t<position>` (SPEC §7, D-048)."""
    return f"{sha[:16]}-p{page}-t{position}"


def extract_tables(doc: pymupdf.Document, sha: str) -> list[ExtractedTable]:
    """Every Table of the document, in reading order: fake tables dropped, continued tables joined,
    unreadable tables flagged without data (FR-109 … FR-113, FR-119, FR-122)."""
    found: list[ExtractedTable | list[_Part]] = []  # unreadable tables and groups of parts, in reading order
    open_group: list[_Part] | None = None  # the group whose last part is the last table kept so far
    for page in doc:
        first_on_page = True
        for part in _find_parts(page):
            if len(part.column_spans) < 2:
                _drop(part, "fewer than 2 columns")
                continue
            if _is_unreadable(part.rows):
                found.append(_unreadable_table(part, sha))
                open_group, first_on_page = None, False
                continue
            candidates = _header_candidates(part)
            if len(part.rows) == 1 and candidates == 1:
                _drop(part, "no data row")
                continue
            part.header_count = min(candidates, len(part.rows) - 1)
            if not any((cell or "").strip() for row in part.rows[part.header_count :] for cell in row):
                _drop(part, "no filled data cell")
                continue
            if first_on_page and open_group is not None and _continues(open_group, part):
                open_group.append(part)
            else:
                open_group = [part]
                found.append(open_group)
            first_on_page = False
    return [item if isinstance(item, ExtractedTable) else _build(item, sha) for item in found]


def _unreadable_table(part: _Part, sha: str) -> ExtractedTable:
    """A Skipped part: page and id only; its text is never cleaned or sent on (FR-119, FR-122)."""
    table_id = make_table_id(sha, part.page, part.position)
    return ExtractedTable(table_id, [part.page], [(part.page, part.bbox)], unreadable=True)


def _drop(part: _Part, reason: str) -> None:
    """A fake table (FR-110): never shown to the user, only logged at DEBUG."""
    logger.debug("Dropped a table on page %d (position %d): %s", part.page, part.position, reason)


def _find_parts(page: pymupdf.Page) -> list[_Part]:
    """Every table PyMuPDF finds on the page, sorted top to bottom (FR-109)."""
    spans = [
        span
        for block in page.get_text("dict")["blocks"]
        for line in block.get("lines", [])
        for span in line["spans"]
        if span["text"].strip()
    ]
    found = sorted(page.find_tables().tables, key=lambda t: (t.bbox[1], t.bbox[0]))
    parts = []
    for position, table in enumerate(found, start=1):
        boxes = [list(row.cells) for row in table.rows]
        parts.append(
            _Part(
                page=page.number + 1,
                position=position,
                bbox=tuple(table.bbox),
                rows=table.extract(),
                boxes=boxes,
                bold=[_row_is_bold(row.bbox, spans) for row in table.rows],
                column_spans=_column_spans(boxes, table.bbox),
            )
        )
    return parts


def _row_is_bold(row_box: Box, spans: list[dict]) -> bool:
    """Every text span whose centre lies in the row is bold (font flag), and there is one."""
    x0, y0, x1, y1 = row_box
    inside = [
        span
        for span in spans
        if x0 <= (span["bbox"][0] + span["bbox"][2]) / 2 <= x1 and y0 <= (span["bbox"][1] + span["bbox"][3]) / 2 <= y1
    ]
    return bool(inside) and all(span["flags"] & pymupdf.TEXT_FONT_BOLD for span in inside)


def _column_spans(boxes: list[list[Box | None]], bbox: Box) -> list[tuple[float, float]]:
    """Each column's horizontal extent, from its real cells: a merged cell starts at its own column
    but ends further right, so the column ends at the smallest right edge among its cells. A column
    without any real cell (merged in every row) borrows its neighbours' edges."""
    count = len(boxes[0]) if boxes else 0
    spans: list[tuple[float, float]] = []
    for index in range(count):
        cells = [row[index] for row in boxes if row[index] is not None]
        if cells:
            spans.append((min(cell[0] for cell in cells), min(cell[2] for cell in cells)))
        else:
            start = spans[-1][1] if spans else bbox[0]
            spans.append((start, start))
    return spans


def _is_unreadable(rows: list[list[str | None]]) -> bool:
    """At least a quarter of the filled cells contain the replacement character (FR-119)."""
    filled = [cell for row in rows for cell in row if cell and cell.strip()]
    garbled = [cell for cell in filled if REPLACEMENT_CHARACTER in cell]
    return bool(filled) and len(garbled) >= UNREADABLE_SHARE * len(filled)


def _header_candidates(part: _Part) -> int:
    """How many top rows show a header clue, in a row from the top, at most 3 (FR-113 step 1)."""
    count = 0
    for index in range(min(MAX_HEADER_ROWS, len(part.rows))):
        if not _has_header_clue(part, index):
            break
        count += 1
    return count


def _has_header_clue(part: _Part, index: int) -> bool:
    """A horizontally merged cell, bold text over a non-bold row below, or no data value."""
    merged = any(
        box is not None and box[2] > part.column_spans[col][1] + MERGE_TOLERANCE
        for col, box in enumerate(part.boxes[index])
    )
    bold = part.bold[index] and not all(part.bold[index + 1 :])
    return merged or bold or not any(_is_data_value(cell) for cell in part.rows[index])


def _is_data_value(cell: str | None) -> bool:
    """A cell that parses as a number under FR-116/117, except a four-digit year 1900–2100."""
    if cell is None or cell.strip() in MISSING_VALUES:
        return False
    text = cell.strip()
    if YEAR_LABEL.fullmatch(text) and int(text) in YEAR_RANGE:
        return False
    series, _hints = clean_column([text])
    return series.dtype != object


def _header_names(part: _Part) -> list[str]:
    """The flattened names of the part's header rows (FR-113 steps 2–4); cells pass their horizontal
    span only, as `flatten_headers` expects (S01-D-006)."""
    count = part.header_count
    spans = [[None if box is None else (box[0], box[2]) for box in row] for row in part.boxes[:count]]
    return flatten_headers(part.rows[:count], spans, part.column_spans)


def _continues(group: list[_Part], part: _Part) -> bool:
    """FR-111: `part` is the first table on the page after the group's last part, which was the last
    table on its page; same column count; and `part` repeats the header or has none."""
    last = group[-1]
    if part.page != last.page + 1 or len(part.column_spans) != len(last.column_spans):
        return False
    if part.header_count == 0:  # no header clue in its first row: a plain continuation
        return True
    return _header_names(part) == _header_names(group[0])


def _build(group: list[_Part], sha: str) -> ExtractedTable:
    """Join the parts' data rows, flatten the first part's header and clean the data (FR-112 … 118)."""
    first = group[0]
    names = _header_names(first)
    rows = [row for part in group for row in part.rows[part.header_count :]]
    frame, hints = build_dataframe(names, rows)
    return ExtractedTable(
        table_id=make_table_id(sha, first.page, first.position),
        pages=[part.page for part in group],
        parts=[(part.page, part.bbox) for part in group],
        columns=names,
        frame=frame,
        hints=hints,
        row_headers=row_headers(frame),
    )
