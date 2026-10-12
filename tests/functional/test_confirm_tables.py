"""Table confirmation in the chat (spec 03 FR-316, FR-319, FR-320, FR-321): AppTest smoke tests,
staged verification (D-118)."""

import copy

from tests.stubs import StubAnalysisRunner, analysis_result, analyst_catalog_entry as catalog_entry

ENTRY = catalog_entry()
OTHER_ID = "bbbbbbbbbbbbbbbb-p2-t1"


def paused_result() -> dict:
    """A run stopped at the confirmation: one answerable part, its table ticked, one other Candidate."""
    result = analysis_result()
    result.update(answer=None, answer_status=None, part_outcomes=[], code_attempts=0, code_draft=None,
                  sandbox_result=None, attempts_history=[], confirmation=None)
    result["confirmation_request"] = {"parts": [{
        "number": 1, "text": "What is revenue?", "answerable": True, "selected": [ENTRY.table_id], "reason": "",
        "candidates": [
            {"table_id": ENTRY.table_id, "name": ENTRY.name, "document": ENTRY.source_file, "pages": list(ENTRY.pages)},
            {"table_id": OTHER_ID, "name": "Net sales by region", "document": "acme.pdf", "pages": [2]},
        ],
    }]}
    return result


def test_pause_offers_candidates_and_calculate_resumes_with_the_choice(start_app, monkeypatch) -> None:
    """VC-315, VC-318, VC-319, VC-320 (UI) smoke: the toggle starts on; the run pauses with the
    Selected table ticked and the other Candidate unticked; Calculate resumes with the new choice."""
    # Given: a runner that pauses, and a resume that finishes the run
    runner = StubAnalysisRunner([paused_result()])
    resumes = []

    def resume(thread_id, reply, deps, *, on_update=None):
        resumes.append((thread_id, copy.deepcopy(reply)))
        return analysis_result()

    monkeypatch.setattr("ui.analysis.run_analysis", runner)
    monkeypatch.setattr("ui.analysis.resume_analysis", resume)
    at = start_app()
    assert at.toggle[0].label == "Confirm tables before calculating" and at.toggle[0].value is True

    # When: a question is sent
    at.chat_input[0].set_value("What is revenue?").run()

    # Then: the run started with confirmation on and waits with the tables offered
    assert not at.exception and runner.calls[0]["confirm_tables"] is True
    assert any("Before I calculate, check the tables I picked:" in item.value for item in at.markdown)
    assert any("Waiting for your confirmation" in item.value for item in at.text)
    assert [box.value for box in at.checkbox] == [True, False]
    assert at.chat_input[0].disabled and not resumes

    # When: the user swaps the table and calculates
    at.checkbox[0].uncheck()
    at.checkbox[1].check()
    thread_id = at.session_state["messages"][-1]["thread_id"]
    at.button(key=f"confirm-calculate-{thread_id}").click().run()

    # Then: the same thread resumes with the chosen table and the answer is shown
    assert not at.exception
    assert resumes == [(thread_id, {"action": "calculate", "tables": {1: [OTHER_ID]}})]
    assert any("1,288.7" in item.value for item in at.markdown)
    assert not at.chat_input[0].disabled


def test_toggle_off_starts_runs_without_confirmation(start_app, monkeypatch) -> None:
    """VC-318 smoke: switching the toggle off → the next run is started with confirmation off."""
    # Given
    runner = StubAnalysisRunner([analysis_result()])
    monkeypatch.setattr("ui.analysis.run_analysis", runner)
    at = start_app()

    # When
    at.toggle[0].set_value(False).run()
    at.chat_input[0].set_value("What is revenue?").run()

    # Then
    assert not at.exception and runner.calls[0]["confirm_tables"] is False
