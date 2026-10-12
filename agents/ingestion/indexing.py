"""Step 3 of the Ingestion agent: turn validated answers into Index records and store them
(spec 01 FR-136 … FR-141, FR-149).

Pure functions (no I/O):
- `assemble_metadata`: LLM meaning + facts held by code → `TableMetadata` (FR-136, BR-101);
- `index_metadata`: `TableMetadata` → the flat metadata dict of an Index record (SPEC §7);
- `exceeds_size_guard`: would that dict be too big for Pinecone (FR-141);
- `embedding_text`: the text that gets embedded (FR-137);
- `entry_from_record`: an Index record read back → `CatalogEntry`.

Storing:
- `write_document`: the four steps of `index` in the safe order, with rollback (FR-138 … FR-140);
- `load_catalog`: every Index record as a `CatalogEntry` (FR-149).
"""

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from agents.ingestion.pdf.cleaning import dtype_name, rows_as_text
from agents.ingestion.schemas import CatalogEntry, ColumnMetadata, ExtractedTable, TableEnrichment, TableMetadata
from services.llm import translate_proxy_errors
from services.settings import Settings
from services.table_store import delete_tables, write_table
from services.vector_store import delete_records, find_versions, list_records, open_index, upsert_records

logger = logging.getLogger(__name__)

# Code constants (spec 01 §7), not configuration.
ROW_HEADERS_STORED = 50  # row headers in the embedding text and in the Index record
PREVIEW_ROWS = 5
PREVIEW_CELL_CHARS = 40
PREVIEW_MAX_CHARS = 2_000
METADATA_LIMIT_BYTES = 38 * 1024  # Pinecone allows 40 KB of metadata per record


def assemble_metadata(enrichment: TableEnrichment, table: ExtractedTable, source_file: str) -> TableMetadata:
    """Combine the LLM's meaning with the facts extraction produced (FR-136, BR-101, D-062).

    Columns follow the extraction's order and are matched by name; dtypes, ids, pages and row
    headers are never read from the LLM's answer.
    """
    assert table.frame is not None  # an unreadable Table is a Skipped part and never gets here
    described = {column.name: column for column in enrichment.columns}
    columns = []
    for name in table.columns:
        if name not in described:  # `validate` rules this out; fail loudly if it is ever skipped
            raise ValueError(f"The answer does not describe column {name!r}.")
        columns.append(
            ColumnMetadata(
                name=name,
                description=described[name].description,
                unit=described[name].unit,
                dtype=dtype_name(table.frame[name]),
            )
        )
    return TableMetadata(
        table_id=table.table_id,
        name=enrichment.name,
        description=enrichment.description,
        columns=columns,
        row_headers=table.row_headers,
        source_file=source_file,
        pages=table.pages,
    )


def _preview(table: ExtractedTable) -> str:
    """The column names and the first rows as compact text, cut as the Index record requires."""
    assert table.frame is not None
    header = " | ".join(name[:PREVIEW_CELL_CHARS] for name in table.columns)
    rows = rows_as_text(table.frame, PREVIEW_ROWS, max_cell=PREVIEW_CELL_CHARS)
    return "\n".join([header, *rows])[:PREVIEW_MAX_CHARS]


def index_metadata(
    metadata: TableMetadata, table: ExtractedTable, document_sha: str, ingested_at: datetime | None = None
) -> dict[str, Any]:
    """The flat metadata of the Index record (SPEC §7): strings, numbers and lists of strings only."""
    assert table.frame is not None
    stamp = ingested_at if ingested_at is not None else datetime.now(UTC)
    columns_info = [column.model_dump() for column in metadata.columns]
    return {
        "table_id": metadata.table_id,
        "name": metadata.name,
        "description": metadata.description,
        "columns": [column.name for column in metadata.columns],
        "columns_info": json.dumps(columns_info, ensure_ascii=False),
        "row_headers": metadata.row_headers[:ROW_HEADERS_STORED],
        "row_headers_total": len(metadata.row_headers),
        "source_file": metadata.source_file,
        "pages": [str(page) for page in metadata.pages],
        "document_sha": document_sha,
        "n_rows": len(table.frame),
        "n_cols": len(table.columns),
        "ingested_at": stamp.isoformat(),
        "preview": _preview(table),
    }


def exceeds_size_guard(flat_metadata: Mapping[str, Any]) -> bool:
    """True when the record's metadata is over 38 KB, measured as UTF-8 JSON bytes (FR-141, D-064)."""
    size = len(json.dumps(flat_metadata, ensure_ascii=False).encode("utf-8"))
    return size > METADATA_LIMIT_BYTES


def embedding_text(metadata: TableMetadata) -> str:
    """The text that is embedded for one Table (FR-137, D-064): no file name, no page.

    Four lines: name, description, columns with their descriptions and units, and the first 50 row
    headers (`and N more` when there are more; the line is left out when there are none).
    """
    columns = "; ".join(
        f"{column.name} ({column.description}, {column.unit})" if column.unit else f"{column.name} ({column.description})"
        for column in metadata.columns
    )
    lines = [f"Name: {metadata.name}", f"Description: {metadata.description}", f"Columns: {columns}"]
    if metadata.row_headers:
        shown = ", ".join(metadata.row_headers[:ROW_HEADERS_STORED])
        hidden = len(metadata.row_headers) - ROW_HEADERS_STORED
        lines.append(f"Row headers: {shown}" + (f" and {hidden} more" if hidden > 0 else ""))
    return "\n".join(lines)


def entry_from_record(record: Mapping[str, Any]) -> CatalogEntry:
    """Rebuild a `CatalogEntry` from an Index record's metadata (SPEC §7 "Catalog interface").

    Pinecone returns numbers as floats; pydantic accepts whole floats as ints.
    """
    return CatalogEntry(
        table_id=record["table_id"],
        name=record["name"],
        description=record["description"],
        columns=[ColumnMetadata(**column) for column in json.loads(record["columns_info"])],
        row_headers=list(record["row_headers"]),
        source_file=record["source_file"],
        pages=[int(page) for page in record["pages"]],
        document_sha=record["document_sha"],
        ingested_at=record["ingested_at"],
        preview=record["preview"],
        n_rows=record["n_rows"],
        n_cols=record["n_cols"],
        row_headers_total=record["row_headers_total"],
    )


# --- Storing (FR-138 … FR-140, FR-149) -----------------------------------------------------------


@dataclass(frozen=True)
class TableToIndex:
    """One valid Table, ready to store: its metadata, its full data and its flat Index metadata.

    `record_metadata` is built (and size-checked) when the metadata is assembled (FR-141), so what is
    stored is exactly what passed the guard.
    """

    metadata: TableMetadata
    frame: pd.DataFrame
    record_metadata: dict[str, Any]


@dataclass(frozen=True)
class WriteResult:
    """What `write_document` did. `previous_removed` is False when step 4 failed (FR-140)."""

    table_ids: list[str]
    previous_removed: bool


def load_catalog(settings: Settings, index: Any = None) -> list[CatalogEntry]:
    """Every Table in the Index as a `CatalogEntry` (FR-149, SPEC §7 "Catalog interface").

    Raises a spec 00 `VectorStoreError` leaf when Pinecone cannot be read (FR-163).
    """
    index = index if index is not None else open_index(settings)
    return [entry_from_record(record) for record in list_records(index, settings.PINECONE_NAMESPACE)]


def write_document(
    settings: Settings,
    source_file: str,
    document_sha: str,
    tables: Sequence[TableToIndex],
    *,
    embeddings: Any,
    index: Any,
) -> WriteResult:
    """Store a Document's Tables so that a failure never leaves a half-written version (D-067, BR-105).

    First a read: ask Pinecone which records already carry `source_file` (S01-D-018). Then the
    writes, in this order:
    1. embed every embedding text (the likeliest failure, and free to discard);
    2. write each Table's Parquet file;
    3. upsert the Index records, in batches;
    4. delete the records and files of the earlier version of this file.

    A failure in the lookup or in steps 1-3 removes what this run wrote and re-raises the leaf
    error (FR-139); the earlier version stays complete. A failure in step 4 keeps the new version
    and is reported through `previous_removed=False` (FR-140). With no Tables nothing is touched
    (FR-142).
    """
    if not tables:
        return WriteResult([], True)
    namespace = settings.PINECONE_NAMESPACE
    new_ids = [table.metadata.table_id for table in tables]

    existing_ids = {record["table_id"] for record in find_versions(index, namespace, source_file)}
    stale_ids = sorted(existing_ids - set(new_ids))  # earlier versions: other bytes, so other ids
    own_ids = [table_id for table_id in new_ids if table_id not in existing_ids]  # this run creates these

    texts = [embedding_text(table.metadata) for table in tables]
    with translate_proxy_errors():
        vectors = embeddings.embed_documents(texts)

    try:
        for table in tables:
            write_table(table.metadata.table_id, table.frame)
        upsert_records(
            index,
            namespace,
            [
                {"id": table.metadata.table_id, "values": vector, "metadata": table.record_metadata}
                for table, vector in zip(tables, vectors, strict=True)
            ],
        )
    except Exception:
        _remove_own_writes(index, namespace, own_ids)
        raise

    try:
        delete_records(index, namespace, stale_ids)
        delete_tables(stale_ids)
    except Exception:  # noqa: BLE001 (any failure here leaves the new version complete; the chat says so)
        logger.debug("Removing the previous version of %s failed", source_file, exc_info=True)
        return WriteResult(new_ids, previous_removed=False)
    return WriteResult(new_ids, previous_removed=True)


def _remove_own_writes(index: Any, namespace: str, table_ids: list[str]) -> None:
    """Best effort: remove records and files this run created. Each removal is tried on its own."""
    for remove in (lambda: delete_records(index, namespace, table_ids), lambda: delete_tables(table_ids)):
        try:
            remove()
        except Exception:  # noqa: BLE001 (the original failure is the one that matters)
            logger.debug("Rolling back a failed write also failed", exc_info=True)
