"""Deferred graph verification consolidated in the final iteration (D-118)."""

import pandas as pd
import pytest

from agents.ingestion.graph import build_graph, run_ingestion, resume_ingestion
from agents.ingestion.state import IngestionDeps
from agents.ingestion.schemas import TableContext
from services.errors import ProxyUnreachableError
from tests.pdf_fixtures import make_pdf, text_page, image_only_page, encrypt
from tests.stubs import FakeEmbeddings, FakePineconeIndex, ScriptedChatModel, extracted_table, enrichment_for


def setup_run(settings, answers):
    model, index = ScriptedChatModel(answers), FakePineconeIndex()
    deps = IngestionDeps(settings, FakeEmbeddings(), index, make_chat_model=model.build)
    return build_graph(deps), deps, model, index


def synthetic_tables(monkeypatch, tables):
    monkeypatch.setattr("agents.ingestion.nodes.read_tables", lambda *_: tables)
    monkeypatch.setattr("agents.ingestion.nodes.read_context", lambda *_: TableContext(caption="Sales"))
    monkeypatch.setattr("agents.ingestion.graph.table_upper_bound", lambda _: (len(tables), 1))


def test_exported_graph_includes_the_actual_conditional_routes(make_settings):
    """VC-162: the exported diagram shows the execution routes, retry loop and both pauses."""
    # Given
    graph, *_ = setup_run(make_settings(), [])
    # When
    edges = {(edge.source, edge.target) for edge in graph.get_graph().edges}
    # Then
    assert {("load_pdf", "extract_tables"), ("extract_tables", "ask_unreadable"),
            ("validate", "enrich"), ("next_table", "ask_skipped"), ("ask_skipped", "index")} <= edges


@pytest.mark.parametrize("kind,vc", [("damaged", "VC-105"), ("encrypted", "VC-106"), ("scanned", "VC-107")])
def test_rejected_documents_leave_every_store_unchanged(kind, vc, make_settings, table_store_dir):
    """VC-105/106/107: refused documents make no model, embedding or index calls or writes."""
    # Given
    data = {"damaged": b"not a pdf", "encrypted": encrypt(make_pdf(text_page("Text"))),
            "scanned": make_pdf(image_only_page())}[kind]
    graph, deps, model, index = setup_run(make_settings(), [])
    # When
    result = run_ingestion(graph, deps, "report.pdf", data)
    # Then
    assert result.status == "finished" and result.values["outcome"]["status"] == "failed"
    assert not model.calls and not deps.embeddings.calls and not index.calls
    assert not table_store_dir.exists() and not deps.runs.thread_ids()


def test_oversized_table_is_offered_at_pause_and_only_others_are_indexed(monkeypatch, make_settings, table_store_dir):
    """VC-144: oversize metadata is skipped before writing and Index N writes only valid tables."""
    # Given
    large = extracted_table([f"Column {i}" for i in range(400)], [["value"] * 400], table_id="large")
    small = extracted_table(["Region", "Sales"], [["North", "10"]], table_id="small")
    synthetic_tables(monkeypatch, [large, small])
    answer = enrichment_for(large)
    for column in answer.columns:
        column.description = "x" * 200
    graph, deps, model, index = setup_run(make_settings(), [answer, enrichment_for(small)])
    # When
    paused = run_ingestion(graph, deps, "report.pdf", make_pdf(text_page("Sales")))
    # Then
    assert paused.status == "paused" and paused.question["pause"] == "ask_skipped"
    assert "Index the other 1 table" in paused.question["question"]
    assert not index.calls and not table_store_dir.exists()
    # When
    result = resume_ingestion(graph, deps, paused.thread_id, "index")
    # Then
    assert result.values["outcome"]["status"] == "indexed"
    assert index.ids(deps.settings.PINECONE_NAMESPACE) == ["small"]
    assert sorted(p.name for p in table_store_dir.iterdir()) == ["small.parquet"]


def test_checkpoints_and_updates_keep_only_twenty_rows(monkeypatch, make_settings, table_store_dir):
    """VC-167: every checkpoint/output is light and the finished run releases its full data."""
    # Given
    table = extracted_table(["Region", "Sales"], [[str(i), str(i)] for i in range(200)])
    synthetic_tables(monkeypatch, [table])
    graph, deps, model, index = setup_run(make_settings(), [enrichment_for(table)])
    updates = []
    # When
    result = run_ingestion(graph, deps, "report.pdf", make_pdf(text_page("Sales")),
                           on_update=lambda node, update: updates.append(update))
    # Then
    def check(value):
        assert not isinstance(value, (bytes, pd.DataFrame))
        if isinstance(value, dict):
            if "rows" in value:
                assert len(value["rows"]) <= 20
            for child in value.values():
                check(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                check(child)
    for update in updates:
        check(update)
    for snapshot in graph.get_state_history({"configurable": {"thread_id": result.thread_id}}):
        check(snapshot.values)
    assert not deps.runs.thread_ids()


def test_second_table_model_outage_ends_without_a_pause_or_any_write(monkeypatch, make_settings, table_store_dir):
    """VC-168: a model outage ends immediately, preserves old data and exposes only safe wording."""
    # Given
    tables = [extracted_table(["Region", "Sales"], [["North", "10"]], table_id=str(i)) for i in range(2)]
    synthetic_tables(monkeypatch, tables)
    graph, deps, model, index = setup_run(make_settings(), [enrichment_for(tables[0]), ProxyUnreachableError("private")])
    # When
    result = run_ingestion(graph, deps, "report.pdf", make_pdf(text_page("Sales")))
    # Then
    assert result.status == "finished" and result.question is None
    assert result.values["outcome"]["status"] == "failed"
    assert not result.values["skipped"] and not index.calls and not table_store_dir.exists()
    assert not deps.embeddings.calls and not deps.runs.thread_ids()
    assert all(word not in result.values["outcome"]["message"] for word in ("private", "proxy", "LiteLLM", "Pinecone"))
