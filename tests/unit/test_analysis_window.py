"""Analysis conversation-window smoke test: staged verification (D-118)."""

from ui.analysis_window import build_window


def test_window_contains_only_last_finished_analysis_turns() -> None:
    """Window smoke: questions pair with their own Analysis answers, excluding ingestion and pending runs."""
    # Given
    messages = [{"kind": "analysis", "status": "finished", "question": f"Question {i}", "content": f"Answer {i}"} for i in range(6)]
    messages += [{"kind": "ingestion", "status": "finished", "content": "Indexed tables"},
                 {"kind": "analysis", "status": "queued", "question": "Pending", "content": ""}]
    # When
    window = build_window(messages)
    # Then
    assert [(turn.question, turn.answer) for turn in window] == [(f"Question {i}", f"Answer {i}") for i in range(2, 6)]
    assert build_window([]) == []
