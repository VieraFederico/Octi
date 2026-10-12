"""Public tracing API smoke tests: staged verification (D-118)."""

import json
from dataclasses import replace

from langchain_core.tracers.langchain import wait_for_all_tracers
from langsmith import Client

from agents.analyst.graph import mask_sandbox_output, run_analysis
from agents.analyst.schemas import CodeDraft, FinalAnswer, PartSelection, TableSelection
from services.sandbox import SandboxResult
from tests.stubs import TraceRecordingSession, analyst_deps, analyst_catalog_entry as catalog_entry, query_plan


def test_traced_run_masks_every_payload_and_updates_root_metadata(make_settings, tmp_path) -> None:
    """Trace smoke: runs retain their labels and execution metrics without raw sandbox output."""
    # Given
    entry = catalog_entry()
    session = TraceRecordingSession()
    client = Client(api_url="https://traces.example.test", api_key="fake-tracing-key", info={},
                    session=session, auto_batch_tracing=False, omit_traced_runtime_info=True,
                    hide_inputs=mask_sandbox_output, hide_outputs=mask_sandbox_output)
    selection = TableSelection(parts=[PartSelection(part=1, table_ids=[entry.table_id], verdict="answerable", missing="")])
    emitted = '{"parts": [{"part": 1, "status": "answered", "values": {"Revenue": 1288.7}}]}'
    result = SandboxResult(0, False, "sandbox-output-marker\n" + emitted, "sandbox-error-marker")
    deps, _, _ = analyst_deps(make_settings(LANGSMITH_TRACING="true"), tmp_path,
        [query_plan("Question"), selection, CodeDraft(code="emit(parts)", approach="Read the row."), FinalAnswer(text="Revenue is 1,288.7.")], [result])
    deps = replace(deps, tracing_client=client)

    # When
    state = run_analysis("Question", [], deps, False, thread_id="analysis-smoke")
    wait_for_all_tracers()

    # Then
    assert state["answer_status"] == "answered" and session.payloads
    serialized = json.dumps(session.payloads, default=str)
    assert "sandbox-output-marker" not in serialized and "sandbox-error-marker" not in serialized
    assert "stdout_bytes" in serialized and "stderr_bytes" in serialized
    roots = [payload for payload in session.payloads if payload.get("name") == "Analysis: Question" and not payload.get("parent_run_id")]
    assert any(payload.get("extra", {}).get("metadata", {}).get("answer_status") == "answered" for payload in roots)
    assert any(payload.get("extra", {}).get("metadata", {}).get("parts_answered") == 1 for payload in roots)
    assert any(payload.get("name") == "execute" for payload in session.payloads)
    client.close()


def test_tracing_off_never_builds_a_tracing_client(make_settings, tmp_path, monkeypatch) -> None:
    """Trace smoke: disabling tracing leaves analysis usable without any tracing service access."""
    # Given
    def forbidden(*_args, **_kwargs):
        raise AssertionError("No tracing client may be built")
    monkeypatch.setattr("agents.analyst.graph.make_langsmith_client", forbidden)
    deps, _, _ = analyst_deps(make_settings(), tmp_path, [], [], entries=[])

    # When
    state = run_analysis("Question", [], deps, False)

    # Then
    assert state["answer_status"] == "cannot_answer" and state["error"] is None
