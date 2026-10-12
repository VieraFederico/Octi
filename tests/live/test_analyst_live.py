"""Student-run ingestion → real Analyst check, with isolated storage and cleanup."""

from numbers import Real
from uuid import uuid4

import pytest

from agents.analyst.graph import run_analysis
from agents.analyst.state import make_deps as analyst_deps
from agents.ingestion.graph import build_graph, resume_ingestion, run_ingestion
from agents.ingestion.indexing import entry_from_record
from agents.ingestion.pdf.tables import document_sha
from agents.ingestion.state import make_deps as ingestion_deps
from services.settings import REPO_ROOT, get_settings
from services.vector_store import delete_records


@pytest.mark.live
def test_acme_question_answers_with_numeric_evidence(table_store_dir) -> None:
    """VC-245: real services answer revenue using the expected table, without wording assertions."""
    settings = get_settings().model_copy(update={"PINECONE_NAMESPACE": "octi-analyst-test-" + uuid4().hex})
    filename = "acme-annual-report-2023.pdf"
    pdf = (REPO_ROOT / "data" / "sample_pdfs" / filename).read_bytes()
    prefix = document_sha(pdf)[:16]
    expected = f"{prefix}-p1-t1"
    ids = {f"{prefix}-p1-t1", f"{prefix}-p1-t2", f"{prefix}-p2-t1", f"{prefix}-p3-t1", f"{prefix}-p4-t1"}
    deps = ingestion_deps(settings)
    graph = build_graph(deps)
    thread = uuid4().hex
    try:
        ingestion = run_ingestion(graph, deps, filename, pdf, thread_id=thread)
        while ingestion.status == "paused":
            choices = {choice["value"] for choice in ingestion.question["choices"]}
            choice = "continue" if "continue" in choices else "index" if "index" in choices else "cancel"
            ingestion = resume_ingestion(graph, deps, thread, choice)
        assert ingestion.values["outcome"]["status"] == "indexed"
        catalog = [entry_from_record(item["record_metadata"]) for item in ingestion.values["assembled"]]
        result = run_analysis("What was ACME's net revenue in 2023?", [], analyst_deps(settings, catalog=catalog),
                              confirm_tables=False)
        assert result["error"] is None
        assert result["answer_status"] == "answered"
        values = [value for part in result["part_outcomes"] for value in part.values.values()]
        assert any(isinstance(value, Real) and not isinstance(value, bool) for value in values)
        assert expected in {table for part in result["selection"].parts for table in part.table_ids}
    finally:
        snapshot = graph.get_state({"configurable": {"thread_id": thread}})
        ids.update(item["metadata"]["table_id"] for item in snapshot.values.get("assembled", []))
        deps.runs.close(thread)
        try:
            delete_records(deps.index, settings.PINECONE_NAMESPACE, sorted(ids))
        finally:
            for path in table_store_dir.glob("*.parquet"):
                path.unlink()
