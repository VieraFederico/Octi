"""Analyst node smoke tests: staged verification (D-118)."""

from agents.analyst import nodes
from agents.analyst.schemas import CodeDraft, FinalAnswer, PartOutcome
from tests.analyst_stubs import analyst_deps, catalog_entry, query_plan


def test_retrieval_merges_ranked_phrases_without_reading_table_data(make_settings, tmp_path) -> None:
    """Retrieval smoke: overlapping searches retain the best-ranked tables without loading frames."""
    # Given
    entries = [catalog_entry(table_id=f"table-{i}") for i in range(14)]
    deps, model, runner = analyst_deps(make_settings(), tmp_path, [], [], entries=entries)
    deps.index.query_batches = [
        [(entries[i].table_id, i / 100) for i in range(5)],
        [(entries[i].table_id, i / 10) for i in range(4, 9)],
        [(entries[i].table_id, i / 10) for i in range(9, 14)],
    ]
    plan = query_plan("Question", search_phrases=["first", "second", "third"])

    # When
    update = nodes.retrieve({"plan": plan}, deps)

    # Then
    assert len(update["candidates"]) == 10
    assert [entry.table_id for entry in update["candidates"]] == [f"table-{i}" for i in range(13, 3, -1)]
    assert len(deps.index.query_calls) == 3 and not model.calls and not runner.calls
    assert all(call["top_k"] == 5 and call["include_metadata"] for call in deps.index.query_calls)


def test_unanswered_response_omits_values_and_method(make_settings, tmp_path) -> None:
    """Response smoke: an unanswered calculation supplies reasons and sources without invented results."""
    # Given
    deps, model, _ = analyst_deps(make_settings(), tmp_path, [FinalAnswer(text="The requested row is absent.")], [])
    state = {"plan": query_plan("Question"), "candidates": [], "selection": None,
             "part_outcomes": [PartOutcome(part=1, outcome="missing", reason="The requested row is absent.")],
             "answer_status": "cannot_answer", "code_draft": CodeDraft(code="pass", approach="Multiply by 12345.")}

    # When
    update = nodes.respond(state, deps)

    # Then
    assert update["answer"] == "The requested row is absent."
    assert "12345" not in model.calls[-1][-1].content
    assert "# Method\nnone" in model.calls[-1][-1].content
