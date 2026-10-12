"""Test builders and fakes for the Analyst agent (spec 02).

They live here, not in `tests/stubs.py`, while spec 01 is still being implemented in parallel; spec
02's final iteration moves them into `tests/stubs.py` (D-105).
"""

from collections.abc import Sequence
from datetime import UTC, datetime

from agents.analyst.schemas import QueryPlan, QuestionPart
from agents.ingestion.schemas import CatalogEntry, ColumnMetadata

ColumnSpec = tuple[str, str, str, str]  # (name, unit, dtype, description)

DEFAULT_COLUMNS: tuple[ColumnSpec, ...] = (
    ("Year", "", "int64", "Fiscal year of the figures"),
    ("Revenue (net)", "USD millions", "float64", "Net revenue of the year"),
)
DEFAULT_ROWS: tuple[tuple[str, ...], ...] = (("2021", "1050.2"), ("2022", "1175.4"), ("2023", "1288.7"))


def catalog_entry(
    *,
    table_id: str = "aaaaaaaaaaaaaaaa-p1-t1",
    name: str = "Income statement by year",
    description: str = "Revenue and income of ACME for 2021 to 2023, in USD millions.",
    columns: Sequence[ColumnSpec | ColumnMetadata] = DEFAULT_COLUMNS,
    row_headers: Sequence[str] = (),
    source_file: str = "acme-annual-report-2023.pdf",
    pages: Sequence[int] = (1,),
    preview: str | None = None,
    n_rows: int = len(DEFAULT_ROWS),
    row_headers_total: int | None = None,
) -> CatalogEntry:
    """A valid `CatalogEntry`; the preview defaults to the column-names line plus `DEFAULT_ROWS`."""
    metadata = [
        column if isinstance(column, ColumnMetadata) else ColumnMetadata(
            name=column[0], unit=column[1], dtype=column[2], description=column[3]
        )
        for column in columns
    ]
    if preview is None:
        header = " | ".join(column.name for column in metadata)
        preview = "\n".join([header, *(" | ".join(row) for row in DEFAULT_ROWS)])
    return CatalogEntry(
        table_id=table_id,
        name=name,
        description=description,
        columns=metadata,
        row_headers=list(row_headers),
        source_file=source_file,
        pages=list(pages),
        document_sha="a" * 64,
        ingested_at=datetime(2026, 10, 11, tzinfo=UTC),
        preview=preview,
        n_rows=n_rows,
        n_cols=len(metadata),
        row_headers_total=len(row_headers) if row_headers_total is None else row_headers_total,
    )


def query_plan(*part_texts: str, search_phrases: Sequence[str] = ("annual revenue by year",)) -> QueryPlan:
    """A `QueryPlan` with one part per text, numbered from 1; the standalone question joins the texts."""
    parts = [
        QuestionPart(number=number, text=text, entities=[], metrics=[], periods=[], operations=[])
        for number, text in enumerate(part_texts, start=1)
    ]
    return QueryPlan(standalone_question=" ".join(part_texts), parts=parts, search_phrases=list(search_phrases))
