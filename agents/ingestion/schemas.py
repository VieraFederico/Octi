"""Data shapes of the Ingestion agent (D-084).

This part holds the plain data classes the PDF-reading step produces; the SPEC §7 Pydantic models
(`TableEnrichment`, `TableMetadata`, …) join them in a later iteration.
"""

from dataclasses import dataclass, field

import pandas as pd

Box = tuple[float, float, float, float]  # (x0, y0, x1, y1) in points, origin top-left


@dataclass
class ExtractedTable:
    """One Table as extraction leaves it: facts only, no LLM output (BR-101).

    - `table_id`: `<16 hex of the PDF hash>-p<first page>-t<position on that page>` (D-048).
    - `pages`: every page the Table spans, in order, 1-based (FR-112).
    - `parts`: `(page, box)` of each part, in order; one part unless joined across pages (FR-111).
    - `columns`: the flattened, unique column names (FR-113).
    - `frame`: the cleaned DataFrame (FR-114 … FR-117); `None` for an unreadable table (FR-122).
    - `hints`: per column name, `percent` / `currency: <symbol>` (FR-118).
    - `row_headers`: the first column's labels when it holds text (FR-114).
    - `unreadable`: at least a quarter of the filled cells contain `�` (FR-119); such a table is a
      Skipped part and carries no columns, data, hints or row headers.
    """

    table_id: str
    pages: list[int]
    parts: list[tuple[int, Box]]
    columns: list[str] = field(default_factory=list)
    frame: pd.DataFrame | None = None
    hints: dict[str, list[str]] = field(default_factory=dict)
    row_headers: list[str] = field(default_factory=list)
    unreadable: bool = False


@dataclass(frozen=True)
class TableContext:
    """The text around one Table, by role (FR-123, D-058); a field is `""` when not found.

    - `section`: the nearest heading above it, searched back to earlier pages.
    - `caption`: `Table N` / `Tabla N` / `Cuadro N` just above or just below, else a short block
      directly above.
    - `before` / `after`: the paragraph directly above / below, at most 600 characters each.
    - `footnotes`: the lines right below it that start with a marker or `Note:` / `Source:` …,
      joined with line breaks.
    The five fields total at most 2,000 characters (FR-126).
    """

    section: str = ""
    caption: str = ""
    before: str = ""
    after: str = ""
    footnotes: str = ""
