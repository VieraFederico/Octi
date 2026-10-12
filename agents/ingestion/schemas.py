"""Data shapes of the Ingestion agent (D-084).

Two kinds live here:
- plain dataclasses the PDF-reading step produces (`ExtractedTable`, `TableContext`);
- the SPEC §7 Pydantic models: `TableEnrichment` is what the LLM writes (meaning only, D-062),
  `TableMetadata` is what code assembles from it plus the facts code holds, `CatalogEntry` is a
  `TableMetadata` as read back from the Index (D-080).
"""

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd
from pydantic import BaseModel, Field

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


# --- The LLM's structured output (D-062, D-068) ----------------------------------------------------
# The `Field(description=...)` texts are the field rules the LLM sees, so they are written for it.


class ColumnDescription(BaseModel):
    """The LLM's description of one column."""

    name: str = Field(description="Exactly one of the column names listed under 'Columns', copied character by character.")
    description: str = Field(description="One short phrase saying what the column holds, for which period or group.")
    unit: str = Field(
        max_length=40,
        description=(
            "Unit of the values, at most 40 characters: '%' for percentages, 'USD millions', 'people'... "
            "Use an empty string for labels and codes. Use 'not stated' for a measure whose unit "
            "appears nowhere in the message."
        ),
    )


class TableEnrichment(BaseModel):
    """What the LLM must produce for one Table: only the meaning, never the facts (BR-101)."""

    name: str = Field(
        max_length=80,
        description=(
            "Short name of the table, 3 to 8 words: the measure and its breakdown. "
            "Use the caption's wording without its numbering. Never a placeholder such as 'Table 2'."
        ),
    )
    description: str = Field(
        max_length=600,
        description=(
            "2 to 4 sentences: what is measured, the unit, the period, the scope, "
            "and any footnote that changes how the values are read. At most 600 characters."
        ),
    )
    columns: list[ColumnDescription] = Field(
        description="One entry for every column listed under 'Columns', once each, in the listed order."
    )


# --- Assembled by code (D-062) ---------------------------------------------------------------------


class ColumnMetadata(BaseModel):
    """A column's LLM-written meaning plus the dtype code measured."""

    name: str = Field(description="Column name exactly as extracted from the PDF.")
    description: str = Field(description="What the column holds (from the LLM).")
    unit: str = Field(description="Unit of the values (from the LLM); '' for labels, 'not stated' when unknown.")
    dtype: str = Field(description="'int64', 'float64' or 'text' (from the DataFrame).")


class TableMetadata(BaseModel):
    """Everything the catalog knows about one Table; covers assignment §5.2.4."""

    table_id: str = Field(description="Stable id: <16 hex of the PDF hash>-p<first page>-t<position> (D-048).")
    name: str = Field(description="Table name (from the LLM).")
    description: str = Field(description="Table description (from the LLM).")
    columns: list[ColumnMetadata] = Field(description="Every column, in order.")
    row_headers: list[str] = Field(description="Labels of the first column when it holds text.")
    source_file: str = Field(description="Name of the PDF the Table came from.")
    pages: list[int] = Field(description="Pages the Table spans, 1-based.")


class CatalogEntry(TableMetadata):
    """A `TableMetadata` as read back from an Index record (D-080).

    `row_headers` holds only the first 50 labels the Index stores; `row_headers_total` is the real
    count, so a card can say 'and N more' (S01-D-014).
    """

    document_sha: str = Field(description="Full SHA-256 of the PDF bytes.")
    ingested_at: datetime = Field(description="When the Table was indexed (UTC).")
    preview: str = Field(description="Column names and the first rows as compact text.")
    n_rows: int = Field(description="Number of rows of the Table.")
    n_cols: int = Field(description="Number of columns of the Table.")
    row_headers_total: int = Field(description="How many row headers the Table has in all.")
