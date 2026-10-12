"""Ingestion UI flow smoke tests with offline services (D-118)."""

from tests.stubs import ScriptedIngestionRunner, catalog_entry
from agents.ingestion.state import RunResult


def finished():
    return RunResult("thread", "finished", None, {
        "outcome": {"status": "indexed", "message": "Indexed 1 table from report.pdf"},
        "assembled": [{"record_metadata": catalog_entry().model_dump()}], "skipped": [], "image_pages": [],
    })


def test_upload_pause_resume_and_history(start_app, monkeypatch):
    """VC-101/104/148/150/170 smoke: an upload pauses, resumes, and keeps its result in history."""
    # Given
    pause = {"pause": "ask_unreadable", "intro": "I couldn't read some parts of report.pdf:",
             "bullets": ["page 2 (no selectable text)"], "question": "Continue with the rest, or cancel?",
             "choices": [{"value": "cancel", "label": "Cancel ingestion"}, {"value": "continue", "label": "Continue"}]}
    runner = ScriptedIngestionRunner([RunResult("thread", "paused", pause, {}), finished()])
    monkeypatch.setattr("ui.ingestion.run_ingestion", runner.start)
    monkeypatch.setattr("ui.ingestion.resume_ingestion", runner.resume)
    monkeypatch.setattr("ui.ingestion.make_deps", lambda _: runner.deps)
    monkeypatch.setattr("ui.ingestion.build_graph", lambda _: object())
    monkeypatch.setattr("ui.ingestion.entry_from_record", lambda _: catalog_entry())
    at = start_app()
    at.session_state["pending-upload"] = {"name": "report.pdf", "pdf": b"pdf", "text": "What is revenue?"}
    # When
    at.run()
    # Then
    assert not at.exception and at.chat_input[0].disabled
    assert not at.sidebar.button(key="nav-new").disabled
    assert not any("spec 02" in m.value for m in at.main.markdown)
    # When
    at.button(key="ingestion-thread-continue").click().run()
    at.chat_input[0].set_value("hello").run()
    # Then
    assert not at.exception and len(runner.calls) == 2
    assert any("Indexed 1 table" in s.label for s in at.get("status"))
    assert sum(message.get("kind") == "analysis" for message in at.session_state["messages"]) == 2


def test_duplicate_and_replace_modals(start_app, monkeypatch):
    """VC-102/103 smoke: duplicate and replacement choices appear before any run."""
    from agents.ingestion.pdf.tables import document_sha
    # Given
    at = start_app()
    at.session_state["catalog"] = [catalog_entry(document_sha=document_sha(b"pdf"))]
    at.session_state["pending-upload"] = {"name": "report.pdf", "pdf": b"pdf", "text": ""}
    # When
    at.run()
    # Then
    assert not at.exception and at.button(key="upload-keep")
    assert any("This exact file already exists" in m.value for m in at.markdown)
    # When
    at.button(key="upload-keep").click().run()
    at.session_state["pending-upload"] = {"name": "report.pdf", "pdf": b"new", "text": ""}
    at.run()
    # Then
    assert not at.exception and at.button(key="upload-replace")
    at.button(key="upload-cancel").click().run()
    assert any("Nothing was ingested" in m.value for m in at.main.markdown)
