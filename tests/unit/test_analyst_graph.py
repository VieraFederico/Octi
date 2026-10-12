"""One smoke scenario per Analyst graph route: staged verification (D-118)."""

from dataclasses import replace

import pytest
from pinecone import PineconeConnectionError

from agents.analyst.graph import run_analysis
from agents.analyst.schemas import CodeDraft, FinalAnswer, PartSelection, TableSelection, Turn
from services.errors import ProxyUnreachableError, SandboxUnavailableError, VectorStoreUnreachableError
from services.sandbox import SandboxResult
from tests.analyst_stubs import analyst_deps, catalog_entry, query_plan

CODE = CodeDraft(code='emit([{"part": 1, "status": "answered", "values": {"Revenue": 1288.7}}])', approach="Read the revenue row.")
ANSWER = FinalAnswer(text="Net revenue is 1,288.7 USD millions.")
GOOD = SandboxResult(0, False, '{"parts": [{"part": 1, "status": "answered", "values": {"Revenue": 1288.7}}]}', "")
BAD = SandboxResult(1, False, "", "A scripted calculation error")
OUTAGE = "Something went wrong on my side and I couldn't answer. Please try again in a moment."
ROUTES = (
    "answered", "partial", "empty", "reload", "reload_failure", "select_retry", "select_exhausted",
    "missing_selection", "code_retry", "code_exhausted", "malformed_code_retry", "malformed_code_exhausted",
    "missing_emit", "answer_retry", "answer_template", "answer_failure", "malformed_answer",
    "understand_failure", "select_failure", "generate_failure", "retrieve_failure", "execute_failure",
    "malformed_plan", "empty_plan",
)


@pytest.mark.parametrize("route", ROUTES)
def test_analysis_route_terminates_with_its_evidence(make_settings, tmp_path, route) -> None:
    """Graph route smoke: an Analysis run ends with the status and evidence its route warrants."""
    # Given
    entry = catalog_entry()
    plan = query_plan("What is ACME net revenue in 2023?")
    selection = TableSelection(parts=[PartSelection(part=1, table_ids=[entry.table_id], verdict="answerable", missing="")])
    invalid = TableSelection(parts=[PartSelection(part=1, table_ids=["unknown"], verdict="answerable", missing="")])
    missing = TableSelection(parts=[PartSelection(part=1, table_ids=[entry.table_id], verdict="missing_data", missing="The requested row is absent.")])
    answers, results = [plan, selection, CODE, ANSWER], [GOOD]
    expected, error_kind = "answered", None
    retries = "2"
    if route == "partial":
        plan = query_plan(plan.parts[0].text, "What is the staff count?")
        selection = TableSelection(parts=[selection.parts[0], PartSelection(part=2, table_ids=[entry.table_id], verdict="missing_data", missing="Staff count is absent.")])
        answers, expected = [plan, selection, CODE, ANSWER], "partial"
    elif route == "empty":
        answers, results, expected = [], [], "cannot_answer"
    elif route == "reload_failure":
        answers, expected, error_kind = [], "cannot_answer", "vector_store"
    elif route == "select_retry":
        answers = [plan, invalid, selection, CODE, ANSWER]
    elif route == "select_exhausted":
        answers, results, expected = [plan, invalid, invalid, FinalAnswer(text="I couldn't decide which tables to use.")], [], "cannot_answer"
    elif route == "missing_selection":
        answers, results, expected = [plan, missing, FinalAnswer(text="The requested row is absent.")], [], "cannot_answer"
    elif route == "code_retry":
        answers, results = [plan, selection, CODE, CODE, ANSWER], [BAD, GOOD]
    elif route == "code_exhausted":
        answers, results, expected, retries = [plan, selection, CODE, FinalAnswer(text="I couldn't compute this part.")], [BAD], "cannot_answer", "0"
    elif route == "malformed_code_retry":
        answers = [plan, selection, {"invalid": "code draft"}, CODE, ANSWER]
    elif route == "malformed_code_exhausted":
        answers, results, expected, retries = [plan, selection, CodeDraft(code=" ", approach="none"), FinalAnswer(text="I couldn't compute this part.")], [], "cannot_answer", "0"
    elif route == "missing_emit":
        answers, expected = [plan, selection, CODE, FinalAnswer(text="The requested row is absent.")], "cannot_answer"
        results = [SandboxResult(0, False, '{"parts": [{"part": 1, "status": "missing", "missing": "The requested row is absent."}]}', "")]
    elif route in ("answer_retry", "answer_template"):
        wrong = FinalAnswer(text="Net revenue is 1300.")
        answers = [plan, selection, CODE, wrong, ANSWER if route == "answer_retry" else wrong]
    elif route == "answer_failure":
        answers = [plan, selection, CODE, ProxyUnreachableError("scripted outage")]
    elif route == "malformed_answer":
        answers = [plan, selection, CODE, {"invalid": "answer"}]
    elif route in ("understand_failure", "select_failure", "generate_failure"):
        prefix = {"understand_failure": [], "select_failure": [plan], "generate_failure": [plan, selection]}[route]
        answers, expected, error_kind = [*prefix, ProxyUnreachableError("scripted outage")], "cannot_answer", "llm"
    elif route == "retrieve_failure":
        answers, expected, error_kind = [plan], "cannot_answer", "vector_store"
    elif route == "execute_failure":
        answers, results, expected, error_kind = [plan, selection, CODE], [SandboxUnavailableError("scripted outage")], "cannot_answer", "sandbox"
    elif route == "malformed_plan":
        answers, expected, error_kind = [{"invalid": "plan"}], "cannot_answer", "llm"
    elif route == "empty_plan":
        answers, expected, error_kind = [plan.model_copy(update={"parts": []})], "cannot_answer", "llm"
    deps, model, runner = analyst_deps(make_settings(ANALYST_MAX_RETRIES=retries), tmp_path, answers, results, entries=[] if route == "empty" else [entry])
    if route in ("reload", "reload_failure"):
        deps = replace(deps, catalog=None)
    if route == "reload_failure":
        def failed_catalog(*_args):
            raise VectorStoreUnreachableError("scripted catalog outage")
        deps = replace(deps, load_catalog=failed_catalog)
    if route == "retrieve_failure":
        deps.index.fail_on, deps.index.error = "query", PineconeConnectionError("scripted query outage")
    updates = []

    # When
    state = run_analysis(plan.standalone_question, [Turn(f"Earlier {i}", "Previous answer") for i in range(6)], deps, on_update=lambda name, update: updates.append((name, update)))

    # Then
    names = [name for name, _ in updates]
    assert state["answer_status"] == expected
    assert (state["error"]["kind"] if state["error"] else None) == error_kind
    assert len(state["window"]) == 4
    if error_kind:
        assert names[-1] == "fail" and state["answer"] == OUTAGE
    elif route == "empty":
        assert names == ["library_check", "no_tables"] and not model.calls and not runner.calls
    else:
        assert names[-1] in ("respond", "template") and state["answer"]
    if route in ("select_retry", "select_exhausted"):
        assert names.count("select") == 2
    if route in ("code_retry", "malformed_code_retry"):
        assert state["code_attempts"] == 2 and len(state["attempts_history"]) == 2
        assert state["attempts_history"][0]["failure"] is not None
        assert "# Feedback to fix" in model.calls[-2][-1].content
    if route.startswith("malformed_code"):
        assert state["attempts_history"][0]["feedback"] == "Your answer must be a CodeDraft with non-empty code and approach."
    if route in ("answer_template", "answer_failure", "malformed_answer"):
        assert names[-1] == "template" and "1,288.7" in state["answer"]
    if route in ("missing_selection", "select_exhausted", "malformed_code_exhausted"):
        assert not runner.calls
    if route == "answered":
        assert model.model_names and set(model.model_names) == {deps.settings.LLM_MODEL}
        assert runner.calls[0]["script"].startswith("import json\n")
        assert runner.calls[0]["files"] == sorted(["main.py", f"{entry.table_id}.parquet"])
        assert state["part_outcomes"][0].values["Revenue"] == 1288.7
