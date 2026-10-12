"""Real ingestion shape check; run only by the student with the live marker (VC-164).

Storage is isolated: a unique test namespace and pytest's temporary Table store (S01-D-025).
The production graph is used; model wording is never asserted. Cleanup also runs after failure.
"""

from uuid import uuid4

import pytest

from agents.ingestion.graph import build_graph, run_ingestion, resume_ingestion
from agents.ingestion.pdf.tables import document_sha
from agents.ingestion.state import make_deps
from services.settings import get_settings, REPO_ROOT
from services.table_store import read_table
from services.vector_store import delete_records


@pytest.mark.live
def test_acme_ingestion_has_expected_tables_and_files(table_store_dir):
    """VC-164: the sample's five Tables are indexed with matching pages, ids and readable files."""
    # Given: only this marked, student-run test may load real settings.
    settings = get_settings().model_copy(update={"PINECONE_NAMESPACE": "octi-ingestion-test-" + uuid4().hex})
    source_file = "acme-annual-report-2023.pdf"
    pdf = (REPO_ROOT / "data" / "sample_pdfs" / source_file).read_bytes()
    prefix = document_sha(pdf)[:16]
    expected_ids = {f"{prefix}-p1-t1", f"{prefix}-p1-t2", f"{prefix}-p2-t1", f"{prefix}-p3-t1", f"{prefix}-p4-t1"}
    deps = make_deps(settings)
    graph = build_graph(deps)
    thread = uuid4().hex
    try:
        # When
        result = run_ingestion(graph, deps, source_file, pdf, thread_id=thread)
        while result.status == "paused":
            choices = {choice["value"] for choice in result.question["choices"]}
            choice = "continue" if "continue" in choices else "index" if "index" in choices else "cancel"
            result = resume_ingestion(graph, deps, thread, choice)
        # Then: inspect the write acknowledgement, not an eventually consistent catalog list.
        assert result.values["outcome"]["status"] == "indexed"
        items = result.values["assembled"]
        assert {item["metadata"]["table_id"] for item in items} == expected_ids
        assert [item["metadata"]["pages"] for item in items] == [[1], [1], [2], [3], [4, 5]]
        for item in items:
            record = item["record_metadata"]
            frame = read_table(record["table_id"])
            assert frame.shape == (record["n_rows"], record["n_cols"])
            assert list(frame.columns) == record["columns"]
        assert {path.stem for path in table_store_dir.glob("*.parquet")} == expected_ids
        assert not deps.runs.thread_ids()
    finally:
        # Clean: explicit deterministic ids cover list lag and interrupted partial writes.
        ids = set(expected_ids)
        snapshot = graph.get_state({"configurable": {"thread_id": thread}})
        ids.update(item["metadata"]["table_id"] for item in snapshot.values.get("assembled", []))
        deps.runs.close(thread)
        delete_records(deps.index, settings.PINECONE_NAMESPACE, sorted(ids))
        for path in table_store_dir.glob("*.parquet"):
            path.unlink()
