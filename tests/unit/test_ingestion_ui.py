"""Run presentation and abandonment smoke tests (D-118)."""

from types import SimpleNamespace
from ui.ingestion import ACTIVE, RUNTIME, status_line, abandon_run
from agents.ingestion.state import RunStore
from ui.new_chat import erase


def test_run_status_reports_describing_attempt():
    """VC-148 smoke: a retry identifies its table and attempt."""
    # Given
    values = {"tables": [{"pages": [1]}, {"pages": [3, 4]}], "current": 1, "attempts": 2, "max_retries": 2}
    # When
    line = status_line("enrich", values, "report.pdf")
    # Then
    assert line == "Describing table 2 of 2 (attempt 2 of 3)…"


def test_erasing_a_paused_run_releases_its_data():
    """VC-171 smoke: erasing the conversation abandons a paused run."""
    # Given
    runs = RunStore()
    runs.open("thread", b"pdf")
    state = {"messages": [{}], ACTIVE: {"thread_id": "thread"}, RUNTIME: (None, SimpleNamespace(runs=runs))}
    # When
    erase(state, False)
    # Then
    assert not runs.thread_ids() and not state.get(ACTIVE) and state["messages"] == []
