"""Complete deferred UI scenarios for final verification (D-118)."""

import json
import html
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import streamlit as st

from agents.ingestion.pdf.tables import document_sha
from agents.ingestion.state import RunResult
from services.errors import VectorStoreUnreachableError
from services.settings import REPO_ROOT
from tests.stubs import catalog_entry, ScriptedIngestionRunner


def final_result(status="indexed", entries=None, skipped=None, images=None):
    records = []
    for entry in entries if entries is not None else [catalog_entry()]:
        record = entry.model_dump(mode="json")
        record["columns_info"] = json.dumps(record["columns"])
        record["columns"] = [c.name for c in entry.columns]
        record["pages"] = [str(p) for p in entry.pages]
        records.append({"record_metadata": record})
    message = "Indexed 1 table from report.pdf" if status == "indexed" else "Ingestion cancelled. Nothing from report.pdf was indexed." if status == "cancelled" else "Couldn't index report.pdf. Your previous version is unchanged."
    return RunResult("thread", "finished", None, {"outcome": {"status": status, "message": message},
                     "assembled": records, "skipped": skipped or [], "image_pages": images or []})


@pytest.fixture
def runner_factory(monkeypatch):
    def factory(results, steps=None):
        runner = ScriptedIngestionRunner(results, steps)
        monkeypatch.setattr("ui.ingestion.run_ingestion", runner.start)
        monkeypatch.setattr("ui.ingestion.resume_ingestion", runner.resume)
        monkeypatch.setattr("ui.ingestion.make_deps", lambda _: runner.deps)
        monkeypatch.setattr("ui.ingestion.build_graph", lambda _: object())
        return runner
    return factory


def submit(at, data=b"pdf", text="", name="report.pdf"):
    at.session_state["pending-upload"] = {"name": name, "pdf": data, "text": text}
    return at.run()


@pytest.mark.parametrize("choice", ["keep", "open"])
def test_identical_file_modal_never_starts_ingestion(start_app, runner_factory, choice):
    """VC-102: hash matching wins over name matching; Keep/Open both avoid another run."""
    # Given
    runner = runner_factory([])
    at = start_app()
    at.session_state["catalog"] = [catalog_entry(document_sha=document_sha(b"pdf"))]
    # When
    submit(at)
    # Then
    assert not at.exception and "report.pdf" in " ".join(t.value for t in at.main.text)
    assert at.button(key="upload-keep") and at.button(key="upload-open")
    # When
    at.button(key="upload-" + choice).click().run()
    # Then
    assert not at.exception and runner.calls == []
    if choice == "open":
        assert at.session_state["view"] == "Library" and at.selectbox(key="library-filter").value == "report.pdf"


@pytest.mark.parametrize("choice", ["cancel", "replace"])
def test_replacement_modal_reports_count_and_honors_choice(start_app, runner_factory, choice):
    """VC-103: three existing tables are reported before Cancel or Replace takes effect."""
    # Given
    runner = runner_factory([final_result()])
    at = start_app()
    at.session_state["catalog"] = [catalog_entry(table_id=str(i), document_sha="old") for i in range(3)]
    # When
    submit(at, data=b"new")
    # Then
    assert "3 tables" in " ".join(m.value for m in at.markdown)
    assert not runner.calls and at.button(key="upload-replace")
    # When
    at.button(key="upload-" + choice).click().run()
    # Then
    assert not at.exception and len(runner.calls) == (1 if choice == "replace" else 0)
    if choice == "cancel":
        assert any("Nothing was ingested" in m.value for m in at.main.markdown)


@pytest.mark.parametrize("status", ["indexed", "cancelled", "failed"])
def test_question_follows_any_finished_upload_in_one_turn(start_app, runner_factory, tmp_path, status):
    """VC-101/104: an in-memory attachment precedes the question reply for every ending."""
    # Given
    runner = runner_factory([final_result(status)])
    at = start_app()
    # When
    submit(at, text="What is revenue?")
    # Then
    assert not at.exception and len(runner.calls) == 1 and len(at.chat_message) == 3
    assert "report.pdf" in " ".join(t.value for t in at.main.text)
    assert at.session_state["messages"][-1]["kind"] == "analysis"
    assert not any("spec 02" in m.value for m in at.main.markdown)
    assert at.session_state["messages"][1]["status"] == "finished"
    assert not at.chat_input[0].disabled and not any(b.disabled for b in at.sidebar.button)
    assert "ingestion-pdf" not in at.session_state
    assert not (tmp_path / "report.pdf").exists() and not (REPO_ROOT / "report.pdf").exists()


def paused(kind="ask_unreadable"):
    choices = [{"value": "cancel", "label": "Cancel ingestion"},
               {"value": "continue" if kind == "ask_unreadable" else "index", "label": "Continue" if kind == "ask_unreadable" else "Index 1"}]
    return RunResult("thread", "paused", {"pause": kind, "intro": "Review the skipped parts:",
                     "bullets": ["page 2: <script>caption</script>"], "question": "Continue or cancel?", "choices": choices}, {})


@pytest.mark.parametrize("kind,choice", [("ask_unreadable", "continue"), ("ask_unreadable", "cancel"),
                                        ("ask_skipped", "index"), ("ask_skipped", "cancel")])
def test_both_pauses_resume_inside_the_run_message(start_app, runner_factory, monkeypatch, kind, choice):
    """VC-148/170: streaming controls disable; pauses enable sidebar controls and resume in place."""
    # Given
    runner = runner_factory([paused(kind), final_result("cancelled" if choice == "cancel" else "indexed")],
                            [[("load_pdf", {"page_count": 4}), ("extract_tables", {"tables": [{"pages": [1]}, {"pages": [3, 4]}]}),
                              ("collect_context", {}), ("enrich", {"attempts": 1, "current": 0})], []])
    original = runner.start
    control_calls = []
    original_button, original_input = st.button, st.chat_input
    def button(*args, **kwargs):
        if kwargs.get("key") in ("home", "nav-new", "nav-library"):
            control_calls.append((kwargs["key"], kwargs.get("disabled", False)))
        return original_button(*args, **kwargs)
    def composer(*args, **kwargs):
        control_calls.append(("composer", kwargs.get("disabled", False)))
        return original_input(*args, **kwargs)
    monkeypatch.setattr(st, "button", button)
    monkeypatch.setattr(st, "chat_input", composer)
    def inspect_stream(*args, **kwargs):
        assert st.session_state["active-ingestion"]["status"] == "running"
        assert all((key, True) in control_calls for key in ("home", "nav-new", "nav-library", "composer"))
        return original(*args, **kwargs)
    monkeypatch.setattr("ui.ingestion.run_ingestion", inspect_stream)
    # The UI tree at the pause also retains the controls emitted before streaming.
    at = start_app()
    submit(at, text="Question")
    # Then
    assert not at.exception and at.chat_input[0].disabled
    assert at.chat_input[0].placeholder == "Answer the question above first."
    assert not any(b.disabled for b in at.sidebar.button)
    run = at.chat_message[1]
    assert len(run.button) == 2 and not any("spec 02" in m.value for m in run.markdown)
    assert at.session_state["messages"][1]["lines"] == ["Opened report.pdf (4 pages)", "Found 2 tables (pages 1, 3–4)",
                                                          "Collected context", "Describing table 1 of 2 (attempt 1 of 3)…"]
    # When
    at.button(key="ingestion-thread-" + choice).click().run()
    # Then
    assert not at.exception and runner.calls[-1] == ("resume", choice)
    assert len(at.chat_message) == 3 and not at.chat_input[0].disabled


def test_finished_summary_contains_all_cards_notes_and_survives_navigation(start_app, runner_factory):
    """VC-149/150: two full cards, every skipped/image note and the result persist in history."""
    # Given
    entries = [catalog_entry(name="Regional sales", row_headers=[str(i) for i in range(15)], row_headers_total=15),
               catalog_entry(table_id="other", name="Costs", pages=[4, 5])]
    runner_factory([final_result(entries=entries, skipped=[{"kind": "table", "pages": [7], "caption": "Skipped sales"}], images=[5, 8, 11])])
    at = start_app()
    # When
    submit(at)
    # Then
    assert not at.exception and [e.label for e in at.expander if e.label != "Tables considered"] == ["Regional sales", "Costs"]
    markup = " ".join(e.value for e in at.get("html"))
    assert all(value in markup for value in ("and 5 more", "USD", "int64", "pages 4–5", "Revenue", "Skipped sales"))
    assert any("Pages 5, 8 and 11 contain images" in t.value for t in at.main.text)
    assert at.button(key="ingestion-thread-library")
    # When
    at.button(key="ingestion-thread-library").click().run()
    assert at.selectbox(key="library-filter").value == "report.pdf"
    at.sidebar.button(key="home").click().run()
    at.chat_input[0].set_value("hello").run()
    # Then
    assert not at.exception and [e.label for e in at.expander if e.label != "Tables considered"] == ["Regional sales", "Costs"]


@pytest.mark.parametrize("warn", [True, False])
def test_new_chat_at_a_pause_empties_the_run_without_writes(start_app, runner_factory, warn, table_store_dir):
    """VC-171: both New chat warning modes abandon the paused data without indexing."""
    # Given
    runner = runner_factory([paused()])
    at = start_app()
    at.session_state["new-chat-warn"] = warn
    submit(at)
    # When
    at.sidebar.button(key="nav-new").click().run()
    if warn:
        at.button(key="new-chat-erase").click().run()
    # Then
    assert not at.exception and not at.chat_message and not runner.deps.runs.thread_ids()
    assert len(runner.calls) == 1 and not table_store_dir.exists()


def test_catalog_outage_refuses_upload_and_recovery_retries_before_run(start_app, runner_factory, monkeypatch):
    """VC-172/173: library outages permit questions, refuse uploads, then recover on submission."""
    # Given
    runner = runner_factory([final_result()])
    at = start_app()
    calls = []
    def load(settings):
        calls.append(1)
        if len(calls) < 3:
            raise VectorStoreUnreachableError("private")
        return []
    monkeypatch.setattr("ui.catalog.load_catalog", load)
    at.session_state["catalog-loaded"] = False
    at.session_state["catalog-attempted"] = False
    # When
    at.sidebar.button(key="nav-library").click().run()
    # Then
    assert any("Couldn't load the library" in m.value for m in at.main.markdown)
    assert any("Couldn't load the library" in html.unescape(h.value) for h in at.sidebar.get("html"))
    # When
    at.sidebar.button(key="home").click().run()
    at.chat_input[0].set_value("hello").run()
    submit(at)
    # Then
    assert not runner.calls and any("Couldn't check the library" in m.value for m in at.main.markdown)
    # When
    submit(at)
    # Then
    assert not at.exception and len(runner.calls) == 1 and len(calls) == 3


def test_catalog_order_filter_and_document_navigation(start_app, monkeypatch):
    """VC-152/153/154/155: newest-first catalog, untypeable filtering and Document navigation."""
    # Given
    at = start_app()
    newer = catalog_entry(source_file="new.pdf", name="New sales", ingested_at=datetime(2026, 2, 1, tzinfo=timezone.utc))
    older = catalog_entry(table_id="old", source_file="old.pdf", name="Old sales")
    at.session_state["catalog"] = [older, newer]
    # When
    at.sidebar.button(key="nav-library").click().run()
    # Then
    assert not at.exception and [e.label for e in at.expander] == ["New sales", "Old sales"]
    assert at.selectbox(key="library-filter").options == ["All documents", "new.pdf", "old.pdf"]
    assert at.selectbox(key="library-filter").proto.filter_mode != 0
    # When
    monkeypatch.setattr("streamlit.components.v2.component", lambda *_a, **_k: lambda **_kw: SimpleNamespace(document="old.pdf"))
    at.run()
    # Then
    assert not at.exception and at.selectbox(key="library-filter").value == "old.pdf"
    assert [e.label for e in at.expander] == ["Old sales"]


def test_session_reads_fake_index_once_and_adds_run_results_without_reload(start_app, runner_factory, monkeypatch):
    """VC-152: two Documents load at session start and a third appears without a second read."""
    from agents.ingestion.indexing import load_catalog
    from tests.stubs import FakePineconeIndex
    # Given
    entries = [catalog_entry(table_id="a", source_file="a.pdf"), catalog_entry(table_id="b", source_file="b.pdf")]
    index, loads = FakePineconeIndex(), []
    for item in final_result(entries=entries).values["assembled"]:
        record = item["record_metadata"]
        index.put("octi", record["table_id"], record)
    def load(settings):
        loads.append(1)
        return load_catalog(settings, index=index)
    monkeypatch.setattr("ui.catalog.load_catalog", load)
    runner_factory([final_result()])
    # When
    at = start_app()
    # Then
    assert {entry.source_file for entry in at.session_state["catalog"]} == {"a.pdf", "b.pdf"}
    # When
    submit(at)
    at.sidebar.button(key="nav-library").click().run()
    # Then
    assert not at.exception and len(loads) == 1
    assert set(at.selectbox(key="library-filter").options) == {"All documents", "a.pdf", "b.pdf", "report.pdf"}
