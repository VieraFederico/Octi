"""Analysis UI state/progress smoke tests: staged verification (D-118)."""

from agents.analyst.schemas import PartSelection, TableSelection
from tests.stubs import query_plan
from ui.analysis import ACTIVE, is_busy, queue_analysis, status_line


def test_queued_analysis_is_one_durable_assistant_message() -> None:
    """UI state smoke: a queued question marks the chat busy without storing settings or table data."""
    # Given
    state = {"messages": []}
    # When
    queue_analysis(state, "What is revenue?")
    # Then
    message = state["messages"][0]
    assert state[ACTIVE] is message and is_busy(state)
    assert message["kind"] == "analysis" and message["role"] == "assistant"
    assert message["question"] == "What is revenue?" and message["status"] == "queued"
    assert "settings" not in message and message["values"] == {}


def test_status_lines_use_plan_and_attempt_facts() -> None:
    """Progress smoke: the rewrite, table count and retry counter are visible as plain facts."""
    # Given
    values = {"plan": query_plan("Revenue in 2023?"), "code_attempts": 2,
              "selection": TableSelection(parts=[PartSelection(part=1, table_ids=["table"], verdict="answerable", missing="")])}
    # When
    lines = [status_line(node, values, 2) for node in ("understand", "retrieve", "select", "generate_code", "merge_status")]
    # Then
    assert lines == ["Understood as: Revenue in 2023?", "Searching the library (1 searches)…",
                     "Selected 1 tables", "Running the calculation (attempt 2 of 3)…", "Writing the answer…"]
