"""Index records: metadata assembly, embedding text, size guard, catalog entries (spec 01 FR-136, FR-137, FR-141)."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from agents.ingestion import indexing
from agents.ingestion.indexing import (
    TableToIndex,
    assemble_metadata,
    embedding_text,
    entry_from_record,
    exceeds_size_guard,
    index_metadata,
    load_catalog,
    write_document,
)
from agents.ingestion.schemas import ColumnDescription, TableEnrichment
from services.errors import ProxyUnreachableError, TableStoreError, VectorStoreUnreachableError
from services.table_store import read_table
from services.vector_store import upsert_records
from tests.stubs import FakeEmbeddings, FakePineconeIndex, extracted_table, openai_connection_error

SHA = "b70e6c0d788efb0a" + "0" * 48


@pytest.fixture
def table():
    return extracted_table(
        ["Region", "Revenue / 2023", "Growth"],
        [["North", "$1,200", "5.5%"], ["South", "$900", "-2%"]],
        table_id="b70e6c0d788efb0a-p3-t2",
        pages=(3, 4),
    )


def enrichment(table, **changes) -> TableEnrichment:
    data = {
        "name": "Sales by region",
        "description": "Sales per region in 2023.",
        "columns": [
            ColumnDescription(name="Region", description="Sales region", unit=""),
            ColumnDescription(name="Revenue / 2023", description="Sales in 2023", unit="USD millions"),
            ColumnDescription(name="Growth", description="Year-on-year growth", unit="%"),
        ],
    }
    data.update(changes)
    return TableEnrichment(**data)


# --- assemble_metadata (FR-136, BR-101) ----------------------------------------------------------


def test_facts_come_from_extraction_whatever_the_llm_wrote(table) -> None:
    """VC-138: table_id, pages, dtypes and row headers equal the extraction's; the LLM only adds meaning."""
    # Given an answer whose texts claim other facts
    answer = enrichment(
        table,
        name="Table with id 999 on page 9",
        description="int64 columns on pages 9 and 10; rows: Mars, Venus.",
    )
    # When the metadata is assembled
    metadata = assemble_metadata(answer, table, "report.pdf")
    # Then the facts are the extraction's
    assert metadata.table_id == "b70e6c0d788efb0a-p3-t2"
    assert metadata.pages == [3, 4]
    assert metadata.source_file == "report.pdf"
    assert metadata.row_headers == ["North", "South"]
    assert [(c.name, c.dtype) for c in metadata.columns] == [
        ("Region", "text"),
        ("Revenue / 2023", "int64"),
        ("Growth", "float64"),
    ]
    # And the meaning is the LLM's
    assert metadata.name == answer.name
    assert [(c.description, c.unit) for c in metadata.columns][1] == ("Sales in 2023", "USD millions")


def test_assembly_keeps_the_extraction_column_order_even_if_the_answer_differs(table) -> None:
    """BR-101: columns follow the table, matched by name."""
    answer = enrichment(table)
    answer.columns.reverse()
    metadata = assemble_metadata(answer, table, "report.pdf")
    assert [c.name for c in metadata.columns] == ["Region", "Revenue / 2023", "Growth"]
    assert metadata.columns[0].description == "Sales region"


# --- index_metadata (SPEC §7 "Index record") -----------------------------------------------------


def test_index_metadata_is_flat_and_pinecone_compatible(table) -> None:
    """SPEC §7: the flat metadata fields, with their types."""
    # Given assembled metadata
    metadata = assemble_metadata(enrichment(table), table, "report.pdf")
    # When the flat metadata is built
    flat = index_metadata(metadata, table, SHA)
    # Then every field is a string, number or list of strings (what Pinecone accepts)
    assert set(flat) == {
        "table_id", "name", "description", "columns", "columns_info", "row_headers", "row_headers_total",
        "source_file", "pages", "document_sha", "n_rows", "n_cols", "ingested_at", "preview",
    }  # fmt: skip
    assert flat["table_id"] == "b70e6c0d788efb0a-p3-t2"
    assert flat["columns"] == ["Region", "Revenue / 2023", "Growth"]
    assert flat["pages"] == ["3", "4"]
    assert flat["document_sha"] == SHA
    assert (flat["n_rows"], flat["n_cols"]) == (2, 3)
    assert json.loads(flat["columns_info"])[1] == {
        "name": "Revenue / 2023", "description": "Sales in 2023", "unit": "USD millions", "dtype": "int64",
    }  # fmt: skip
    for value in flat.values():
        assert isinstance(value, str | int | list)


def test_ingested_at_is_utc_iso_8601(table) -> None:
    """SPEC §7: `ingested_at` is an ISO 8601 UTC date-time."""
    metadata = assemble_metadata(enrichment(table), table, "report.pdf")
    stamp = datetime.fromisoformat(index_metadata(metadata, table, SHA)["ingested_at"])
    assert stamp.utcoffset() == UTC.utcoffset(None)
    assert abs((datetime.now(UTC) - stamp).total_seconds()) < 60


def test_row_headers_are_cut_to_fifty_with_the_total(table) -> None:
    """SPEC §7: first 50 row headers plus the total."""
    big = extracted_table(["Name", "Value"], [[f"label {i}", str(i)] for i in range(120)])
    metadata = assemble_metadata(enrichment(big, columns=[
        ColumnDescription(name="Name", description="n", unit=""),
        ColumnDescription(name="Value", description="v", unit="not stated"),
    ]), big, "r.pdf")  # fmt: skip
    flat = index_metadata(metadata, big, SHA)
    assert len(flat["row_headers"]) == 50
    assert flat["row_headers"][0] == "label 0"
    assert flat["row_headers_total"] == 120


def test_preview_is_five_rows_with_the_column_names(table) -> None:
    """SPEC §7: the preview holds the column names and the first 5 rows, compact."""
    rows = [[f"r{i}", str(i), f"{i}.5%"] for i in range(9)]
    big = extracted_table(["Region", "Revenue / 2023", "Growth"], rows)
    flat = index_metadata(assemble_metadata(enrichment(big), big, "r.pdf"), big, SHA)
    lines = flat["preview"].splitlines()
    assert lines[0] == "Region | Revenue / 2023 | Growth"
    assert lines[1:] == ["r0 | 0 | 0.5", "r1 | 1 | 1.5", "r2 | 2 | 2.5", "r3 | 3 | 3.5", "r4 | 4 | 4.5"]


def test_preview_cells_are_cut_to_40_characters_and_the_whole_to_2000() -> None:
    """SPEC §7 / D-064: cells cut to 40 characters; at most 2,000 characters in total."""
    columns = [f"c{i}" for i in range(30)]
    wide = extracted_table(columns, [["x" * 90] * 30 for _ in range(6)])
    answer = TableEnrichment(
        name="Wide", description="d", columns=[ColumnDescription(name=c, description="d", unit="") for c in columns]
    )
    flat = index_metadata(assemble_metadata(answer, wide, "r.pdf"), wide, SHA)
    assert len(flat["preview"]) <= 2000
    narrow = extracted_table(["a"], [["y" * 90]])
    flat = index_metadata(
        assemble_metadata(
            TableEnrichment(name="N", description="d", columns=[ColumnDescription(name="a", description="d", unit="")]),
            narrow,
            "r.pdf",
        ),
        narrow,
        SHA,
    )
    assert flat["preview"].splitlines()[1] == "y" * 40


# --- size guard (FR-141) -------------------------------------------------------------------------


def test_small_metadata_passes_the_guard(table) -> None:
    flat = index_metadata(assemble_metadata(enrichment(table), table, "report.pdf"), table, SHA)
    assert exceeds_size_guard(flat) is False


def test_four_hundred_long_column_descriptions_exceed_the_guard() -> None:
    """VC-144 (function part): 400 columns with long descriptions are over 38 KB."""
    names = [f"Column {i}" for i in range(400)]
    big = extracted_table(names, [["1"] * 400])
    answer = TableEnrichment(
        name="Big",
        description="d",
        columns=[ColumnDescription(name=n, description="a long description of this column. " * 5, unit="u") for n in names],
    )
    flat = index_metadata(assemble_metadata(answer, big, "r.pdf"), big, SHA)
    assert exceeds_size_guard(flat) is True


def test_the_guard_counts_bytes_not_characters() -> None:
    """The limit is on bytes: multi-byte characters weigh more."""
    ascii_flat = {"text": "a" * 20_000}
    accented_flat = {"text": "é" * 20_000}
    assert exceeds_size_guard(ascii_flat) is False
    assert exceeds_size_guard(accented_flat) is True


# --- embedding text (FR-137) ---------------------------------------------------------------------


def test_embedding_text_has_name_description_columns_and_row_headers(table) -> None:
    """VC-139: exactly four lines, units omitted when empty, no file name or page."""
    metadata = assemble_metadata(enrichment(table), table, "report.pdf")
    assert embedding_text(metadata) == (
        "Name: Sales by region\n"
        "Description: Sales per region in 2023.\n"
        "Columns: Region (Sales region); Revenue / 2023 (Sales in 2023, USD millions); Growth (Year-on-year growth, %)\n"
        "Row headers: North, South"
    )
    assert "report.pdf" not in embedding_text(metadata)


def test_embedding_text_cuts_row_headers_at_fifty_with_the_rest_counted() -> None:
    """VC-139: 120 row headers → the first 50, then `and 70 more`."""
    big = extracted_table(["Name", "Value"], [[f"label {i}", str(i)] for i in range(120)])
    answer = TableEnrichment(
        name="Labels",
        description="d",
        columns=[
            ColumnDescription(name="Name", description="n", unit=""),
            ColumnDescription(name="Value", description="v", unit=""),
        ],
    )
    text = embedding_text(assemble_metadata(answer, big, "r.pdf"))
    last = text.splitlines()[-1]
    assert last.startswith("Row headers: label 0, label 1, ")
    assert last.endswith("label 49 and 70 more")
    assert "label 50" not in text


def test_embedding_text_has_no_row_headers_line_when_there_are_none() -> None:
    numeric = extracted_table(["Year", "Sales"], [["2021", "1"], ["2022", "2"]])
    answer = TableEnrichment(
        name="Sales by year",
        description="d",
        columns=[
            ColumnDescription(name="Year", description="y", unit=""),
            ColumnDescription(name="Sales", description="s", unit="USD"),
        ],
    )
    assert "Row headers" not in embedding_text(assemble_metadata(answer, numeric, "r.pdf"))


# --- entry_from_record (SPEC §7 "Catalog interface") ---------------------------------------------


def test_entry_from_record_round_trips_the_flat_metadata(table) -> None:
    """The catalog entry rebuilt from an Index record equals what was written."""
    # Given a record as Pinecone returns it (numbers come back as floats)
    metadata = assemble_metadata(enrichment(table), table, "report.pdf")
    record = index_metadata(metadata, table, SHA)
    record["n_rows"], record["n_cols"], record["row_headers_total"] = 2.0, 3.0, 2.0
    # When the entry is built
    entry = entry_from_record(record)
    # Then it carries the metadata and the extra catalog fields
    assert entry.table_id == metadata.table_id
    assert entry.pages == [3, 4]
    assert entry.columns == metadata.columns
    assert entry.row_headers == ["North", "South"]
    assert entry.row_headers_total == 2
    assert (entry.n_rows, entry.n_cols) == (2, 3)
    assert entry.document_sha == SHA
    assert entry.preview == record["preview"]
    assert entry.ingested_at.tzinfo is not None


# --- load_catalog (FR-149) -----------------------------------------------------------------------


def test_load_catalog_returns_an_entry_per_record(make_settings, table) -> None:
    """The catalog is the Index records read back as entries."""
    # Given an index holding one record
    index = FakePineconeIndex()
    flat = index_metadata(assemble_metadata(enrichment(table), table, "report.pdf"), table, SHA)
    index.put("octi", flat["table_id"], flat)
    # When the catalog is loaded
    entries = load_catalog(make_settings(), index=index)
    # Then it holds that Table
    assert [entry.table_id for entry in entries] == ["b70e6c0d788efb0a-p3-t2"]
    assert entries[0].source_file == "report.pdf"


def test_load_catalog_uses_the_configured_namespace(make_settings, table) -> None:
    """D-064: records live in `PINECONE_NAMESPACE`; another namespace is not the catalog."""
    index = FakePineconeIndex()
    flat = index_metadata(assemble_metadata(enrichment(table), table, "report.pdf"), table, SHA)
    index.put("elsewhere", flat["table_id"], flat)
    assert load_catalog(make_settings(PINECONE_NAMESPACE="octi"), index=index) == []
    assert len(load_catalog(make_settings(PINECONE_NAMESPACE="elsewhere"), index=index)) == 1


def test_load_catalog_failure_is_a_vector_store_error(make_settings) -> None:
    """VC-172 (data part): a failing list raises `VectorStoreUnreachableError`."""
    with pytest.raises(VectorStoreUnreachableError):
        load_catalog(make_settings(), index=FakePineconeIndex(fail_on="list"))


# --- write_document: the safe write order (FR-138 … FR-140, D-067) -------------------------------

NAMESPACE = "octi"
SHA_1 = "1" * 64
SHA_2 = "2" * 64


def document(sha: str, count: int = 2, source_file: str = "report.pdf") -> list[TableToIndex]:
    """`count` Tables of one Document, ready to index (the ids start with the first 16 hex of `sha`)."""
    items = []
    for n in range(count):
        extracted = extracted_table(
            ["Region", "Value"], [["North", f"{n + 1}"], ["South", "2.5"]], table_id=f"{sha[:16]}-p{n + 1}-t1", pages=(n + 1,)
        )
        answer = TableEnrichment(
            name=f"Sales table {n + 1}",
            description="Sales.",
            columns=[
                ColumnDescription(name="Region", description="Region", unit=""),
                ColumnDescription(name="Value", description="Sales", unit="USD"),
            ],
        )
        metadata = assemble_metadata(answer, extracted, source_file)
        assert extracted.frame is not None
        items.append(TableToIndex(metadata, extracted.frame, index_metadata(metadata, extracted, sha)))
    return items


def ids_of(items: list[TableToIndex]) -> list[str]:
    return sorted(item.metadata.table_id for item in items)


def files_in(folder: Path) -> list[str]:
    return sorted(path.stem for path in folder.iterdir()) if folder.exists() else []


def test_the_write_order_is_embed_then_files_then_upserts_then_deletes(
    make_settings, table_store_dir, monkeypatch: pytest.MonkeyPatch
) -> None:
    """VC-140: embeddings, then Parquet writes, then upserts, then deletes, in that order."""
    # Given a previous version in the index and the store, and one shared event list
    events: list[str] = []
    embeddings = FakeEmbeddings(events=events)
    index = FakePineconeIndex(events=events)
    old = document(SHA_1)
    write_document(make_settings(), "report.pdf", SHA_1, old, embeddings=FakeEmbeddings(), index=index)
    events.clear()
    real_write = indexing.write_table
    monkeypatch.setattr(indexing, "write_table", lambda table_id, frame: (events.append("write_table"), real_write(table_id, frame)))
    # When version 2 is written
    new = document(SHA_2)
    write_document(make_settings(), "report.pdf", SHA_2, new, embeddings=embeddings, index=index)
    # Then the order is embed, file writes, one upsert, one delete
    assert events == ["embed", "write_table", "write_table", "upsert", "delete"]


def test_each_record_has_its_parquet_file_with_the_same_dtypes(make_settings, table_store_dir) -> None:
    """VC-140 / BR-108: every record has a file, and the file's dtypes equal the extraction's."""
    items = document(SHA_1, count=3)
    index = FakePineconeIndex()
    write_document(make_settings(), "report.pdf", SHA_1, items, embeddings=FakeEmbeddings(), index=index)
    assert index.ids(NAMESPACE) == files_in(table_store_dir) == ids_of(items)
    for item in items:
        pd.testing.assert_frame_equal(read_table(item.metadata.table_id), item.frame)


def test_the_record_carries_the_vector_of_the_embedding_text(make_settings, table_store_dir) -> None:
    """FR-137 / FR-138: step 1 embeds `embedding_text`, and its vector is the record's `values`."""
    items = document(SHA_1, count=1)
    embeddings = FakeEmbeddings()
    index = FakePineconeIndex()
    write_document(make_settings(), "report.pdf", SHA_1, items, embeddings=embeddings, index=index)
    assert embeddings.calls == [[embedding_text(items[0].metadata)]]
    stored = index.records[NAMESPACE][items[0].metadata.table_id]
    assert stored["values"] == embeddings.embed_documents([embedding_text(items[0].metadata)])[0]
    assert stored["metadata"] == items[0].record_metadata


def test_a_new_version_replaces_the_old_one(make_settings, table_store_dir) -> None:
    """VC-141: report.pdf v1 then v2 (other bytes) → only v2's records and files remain."""
    index = FakePineconeIndex()
    v1, v2 = document(SHA_1, count=3), document(SHA_2, count=2)
    write_document(make_settings(), "report.pdf", SHA_1, v1, embeddings=FakeEmbeddings(), index=index)
    result = write_document(make_settings(), "report.pdf", SHA_2, v2, embeddings=FakeEmbeddings(), index=index)
    assert index.ids(NAMESPACE) == files_in(table_store_dir) == ids_of(v2)
    assert result.table_ids == ids_of(v2)
    assert result.previous_removed is True


def test_another_documents_records_are_left_alone(make_settings, table_store_dir) -> None:
    """BR-110: a Document is identified by file name; other files are not touched."""
    index = FakePineconeIndex()
    other = document("3" * 64, source_file="other.pdf")
    write_document(make_settings(), "other.pdf", "3" * 64, other, embeddings=FakeEmbeddings(), index=index)
    write_document(make_settings(), "report.pdf", SHA_1, document(SHA_1), embeddings=FakeEmbeddings(), index=index)
    write_document(make_settings(), "report.pdf", SHA_2, document(SHA_2), embeddings=FakeEmbeddings(), index=index)
    assert set(ids_of(other)) <= set(index.ids(NAMESPACE))
    assert set(ids_of(other)) <= set(files_in(table_store_dir))


def test_old_versions_found_only_in_pinecone_are_deleted(make_settings, table_store_dir) -> None:
    """VC-174: the older report.pdf is known only to Pinecone (not to any session) → still deleted."""
    # Given an older version written by an earlier session: records and files, nothing else knows
    index = FakePineconeIndex()
    old = document(SHA_1)
    write_document(make_settings(), "report.pdf", SHA_1, old, embeddings=FakeEmbeddings(), index=index)
    # When a new version is written by a fresh call that holds no memory of the old one
    new = document(SHA_2)
    write_document(make_settings(), "report.pdf", SHA_2, new, embeddings=FakeEmbeddings(), index=index)
    # Then the old records and files are gone
    assert not set(ids_of(old)) & set(index.ids(NAMESPACE))
    assert not set(ids_of(old)) & set(files_in(table_store_dir))


def test_the_same_document_twice_leaves_the_same_ids_and_count(make_settings, table_store_dir) -> None:
    """VC-147 (write part) / BR-104: idempotent ids."""
    index = FakePineconeIndex()
    items = document(SHA_1, count=3)
    write_document(make_settings(), "report.pdf", SHA_1, items, embeddings=FakeEmbeddings(), index=index)
    write_document(make_settings(), "report.pdf", SHA_1, items, embeddings=FakeEmbeddings(), index=index)
    assert index.ids(NAMESPACE) == files_in(table_store_dir) == ids_of(items)


def test_an_embedding_failure_writes_nothing_and_keeps_the_old_version(make_settings, table_store_dir) -> None:
    """VC-142: embeddings fail → nothing written, v1 intact; the error is translated."""
    index = FakePineconeIndex()
    v1 = document(SHA_1)
    write_document(make_settings(), "report.pdf", SHA_1, v1, embeddings=FakeEmbeddings(), index=index)
    failing = FakeEmbeddings(error=openai_connection_error())
    with pytest.raises(ProxyUnreachableError):
        write_document(make_settings(), "report.pdf", SHA_2, document(SHA_2), embeddings=failing, index=index)
    assert index.ids(NAMESPACE) == files_in(table_store_dir) == ids_of(v1)


def test_an_upsert_failure_removes_the_new_files_and_keeps_the_old_version(make_settings, table_store_dir) -> None:
    """VC-142: upsert fails after the Parquet writes → v2's files removed, v1 intact."""
    index = FakePineconeIndex()
    v1 = document(SHA_1)
    write_document(make_settings(), "report.pdf", SHA_1, v1, embeddings=FakeEmbeddings(), index=index)
    index.fail_on = "upsert"
    with pytest.raises(VectorStoreUnreachableError):
        write_document(make_settings(), "report.pdf", SHA_2, document(SHA_2), embeddings=FakeEmbeddings(), index=index)
    assert index.ids(NAMESPACE) == files_in(table_store_dir) == ids_of(v1)


def test_a_failure_in_the_second_upsert_batch_removes_the_first_batch_too(make_settings, table_store_dir) -> None:
    """FR-139: records already upserted by this run are removed as well."""
    index = FakePineconeIndex(fail_on="upsert", fail_after=1)
    with pytest.raises(VectorStoreUnreachableError):
        write_document(make_settings(), "report.pdf", SHA_1, document(SHA_1, count=120), embeddings=FakeEmbeddings(), index=index)
    assert index.ids(NAMESPACE) == []
    assert files_in(table_store_dir) == []


def test_a_disk_failure_removes_what_was_written_and_never_upserts(make_settings, table_store_dir, monkeypatch) -> None:
    """FR-139: the second Parquet write fails → the first file is removed, nothing was upserted."""
    real_write = indexing.write_table
    written: list[str] = []

    def flaky(table_id: str, frame: pd.DataFrame) -> None:
        if written:
            raise TableStoreError("Couldn't save the table data.")
        written.append(table_id)
        real_write(table_id, frame)

    monkeypatch.setattr(indexing, "write_table", flaky)
    index = FakePineconeIndex()
    with pytest.raises(TableStoreError):
        write_document(make_settings(), "report.pdf", SHA_1, document(SHA_1, count=3), embeddings=FakeEmbeddings(), index=index)
    assert files_in(table_store_dir) == []
    assert "upsert" not in index.calls


def test_a_failed_rewrite_of_identical_bytes_keeps_the_existing_copy(make_settings, table_store_dir) -> None:
    """BR-105 / S01-D-018: rolling back must not delete the identical version that was already there."""
    index = FakePineconeIndex()
    items = document(SHA_1)
    write_document(make_settings(), "report.pdf", SHA_1, items, embeddings=FakeEmbeddings(), index=index)
    index.fail_on = "upsert"
    with pytest.raises(VectorStoreUnreachableError):
        write_document(make_settings(), "report.pdf", SHA_1, items, embeddings=FakeEmbeddings(), index=index)
    assert index.ids(NAMESPACE) == files_in(table_store_dir) == ids_of(items)


def test_a_failure_deleting_the_old_version_keeps_the_new_one_and_says_so(make_settings, table_store_dir) -> None:
    """VC-143: v2 upserted, deleting v1 fails → v2 present, v1 leftovers present, result flagged."""
    index = FakePineconeIndex()
    v1, v2 = document(SHA_1), document(SHA_2)
    write_document(make_settings(), "report.pdf", SHA_1, v1, embeddings=FakeEmbeddings(), index=index)
    index.fail_on = "delete"
    result = write_document(make_settings(), "report.pdf", SHA_2, v2, embeddings=FakeEmbeddings(), index=index)
    assert result.previous_removed is False
    assert result.table_ids == ids_of(v2)
    assert set(ids_of(v2)) <= set(index.ids(NAMESPACE))
    assert set(ids_of(v1)) <= set(index.ids(NAMESPACE))
    assert set(ids_of(v1)) <= set(files_in(table_store_dir))


def test_a_failure_finding_the_old_version_stops_before_any_write(make_settings, table_store_dir) -> None:
    """S01-D-018: the lookup is a read done first; if it fails nothing has been written."""
    index = FakePineconeIndex(fail_on="fetch_by_metadata")
    embeddings = FakeEmbeddings()
    with pytest.raises(VectorStoreUnreachableError):
        write_document(make_settings(), "report.pdf", SHA_1, document(SHA_1), embeddings=embeddings, index=index)
    assert embeddings.calls == []
    assert index.ids(NAMESPACE) == [] and files_in(table_store_dir) == []


def test_no_tables_means_no_calls_at_all(make_settings, table_store_dir) -> None:
    """FR-142: a Document with nothing to index writes and deletes nothing, and finds nothing."""
    index, embeddings = FakePineconeIndex(), FakeEmbeddings()
    result = write_document(make_settings(), "report.pdf", SHA_1, [], embeddings=embeddings, index=index)
    assert (index.calls, embeddings.calls) == ([], [])
    assert result.table_ids == []
