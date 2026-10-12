"""Analysis chat-flow smoke tests: staged verification (D-118)."""

import pandas as pd
import pytest
import streamlit as st

from agents.ingestion.state import RunResult
from tests.stubs import StubAnalysisRunner, analysis_result
from tests.stubs import ScriptedIngestionRunner


def test_question_streams_evidence_lazily_and_survives_followup(start_app, monkeypatch) -> None:
    """UI flow smoke: answers retain evidence and history; full table data loads only on request."""
    # Given
    runner = StubAnalysisRunner([analysis_result(), analysis_result(answer="A follow-up answer.")])
    controls = []
    original_button, original_input = st.button, st.chat_input
    def button(*args, **kwargs):
        if kwargs.get("key") in ("home", "nav-new", "nav-library"):
            controls.append((kwargs["key"], kwargs.get("disabled", False)))
        return original_button(*args, **kwargs)
    def chat_input(*args, **kwargs):
        controls.append(("composer", kwargs.get("disabled", False)))
        return original_input(*args, **kwargs)
    def run(*args, **kwargs):
        assert all((key, True) in controls for key in ("home", "nav-new", "nav-library", "composer"))
        return runner(*args, **kwargs)
    monkeypatch.setattr(st, "button", button)
    monkeypatch.setattr(st, "chat_input", chat_input)
    monkeypatch.setattr("ui.analysis.run_analysis", run)
    reads = []
    monkeypatch.setattr("ui.analysis.read_table", lambda table_id: reads.append(table_id) or pd.DataFrame({"Revenue": [1288.7]}))
    at = start_app()
    # When
    at.chat_input[0].set_value("What is revenue?").run()
    # Then
    assert not at.exception and not reads
    assert any("1,288.7" in item.value for item in at.markdown)
    assert [item.label for item in at.expander if item.label in ("Tables used", "Code", "Output", "Attempts")] == ["Tables used", "Code", "Output", "Attempts"]
    assert any("Understood as:" in item.value for item in at.text)
    message = at.session_state["messages"][-1]
    entry = message["values"]["candidates"][0]
    key = f"analysis-data-{message['thread_id']}-{entry.table_id}"
    # When: opening the stateful expander through the same widget-state seam as the browser
    at.session_state[key] = True
    at.run()
    # Then
    assert not at.exception and reads == [entry.table_id]
    # When
    at.chat_input[0].set_value("And next year?").run()
    # Then
    assert not at.exception and len(runner.calls) == 2
    assert runner.calls[1]["window"][0].question == "What is revenue?"
    assert any("1,288.7" in item.value for item in at.markdown)


@pytest.mark.parametrize("ending", ["indexed", "cancelled", "failed"])
def test_question_starts_after_every_ingestion_ending(start_app, monkeypatch, ending) -> None:
    """PDF/question flow smoke: the question runs after ingestion finishes, including cancellation or failure."""
    # Given
    ingestion = ScriptedIngestionRunner([RunResult("thread", "finished", None,
        {"outcome": {"status": ending, "message": "Upload finished."}, "assembled": [], "skipped": [], "image_pages": []})])
    analysis = StubAnalysisRunner([analysis_result(status="cannot_answer")])
    monkeypatch.setattr("ui.ingestion.run_ingestion", ingestion.start)
    monkeypatch.setattr("ui.ingestion.make_deps", lambda _: ingestion.deps)
    monkeypatch.setattr("ui.ingestion.build_graph", lambda _: object())
    monkeypatch.setattr("ui.analysis.run_analysis", analysis)
    at = start_app()
    at.session_state["pending-upload"] = {"name": "report.pdf", "pdf": b"offline PDF", "text": "What is revenue?"}
    # When
    at.run()
    # Then
    assert not at.exception and len(ingestion.calls) == len(analysis.calls) == 1
    assert analysis.calls[0]["question"] == "What is revenue?"
    assert [message.get("kind") for message in at.session_state["messages"]] == [None, "ingestion", "analysis"]
    assert not any("spec 02" in item.value for item in at.markdown)


@pytest.mark.parametrize("status", ["partial", "cannot_answer", "error"])
def test_partial_reduced_and_error_messages_render(start_app, monkeypatch, status) -> None:
    """Result-flow smoke: missing data and service failures render their required message layouts."""
    # Given
    runner = StubAnalysisRunner([analysis_result(status=status)])
    monkeypatch.setattr("ui.analysis.run_analysis", runner)
    at = start_app()
    # When
    at.chat_input[0].set_value("Question").run()
    # Then
    assert not at.exception
    labels = [item.label for item in at.expander]
    if status == "error":
        assert at.error and not labels
    elif status == "cannot_answer":
        assert "Tables considered" in labels and "Code" not in labels
    else:
        assert "Tables used" in labels and any("Missing: Question 2" in item.value for item in at.text)
