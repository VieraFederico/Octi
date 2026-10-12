"""Analyst state smoke test: staged verification (D-118)."""

from agents.analyst.graph import run_analysis
from agents.analyst.state import AnalystState
from tests.analyst_stubs import analyst_deps


def test_separate_runs_keep_independent_state(make_settings, tmp_path) -> None:
    """State smoke: earlier run mutations do not become the next run's history or retry state."""
    # Given
    deps, _, _ = analyst_deps(make_settings(), tmp_path, [], [], entries=[])
    first = run_analysis("First question", [], deps)
    first["attempts_history"].append({"code": "earlier code"})

    # When
    second = run_analysis("Second question", [], deps)

    # Then
    assert second["question"] == "Second question" and not second["attempts_history"]
    assert second["code_draft"] is None and second["sandbox_result"] is None
    assert not second["selection_feedback"] and second["error"] is None
    assert set(second) <= set(AnalystState.__annotations__)
