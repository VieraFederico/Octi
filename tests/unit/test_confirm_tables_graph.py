"""Table confirmation in the Analyst graph (spec 03 FR-315 … FR-318, FR-320, FR-321): smoke tests,
staged verification (D-118)."""

from agents.analyst.graph import resume_analysis, run_analysis
from agents.analyst.nodes import CANCELLED_REASON
from agents.analyst.schemas import CodeDraft, FinalAnswer, PartSelection, TableSelection
from services.sandbox import SandboxResult
from tests.stubs import analyst_deps, analyst_catalog_entry as catalog_entry, query_plan

INCOME = catalog_entry(table_id="aaaaaaaaaaaaaaaa-p1-t1", name="Income summary")
REGIONS = catalog_entry(table_id="aaaaaaaaaaaaaaaa-p2-t1", name="Net sales by region")
PLAN = query_plan("What is ACME net revenue in 2023?")
SELECTION = TableSelection(parts=[PartSelection(part=1, table_ids=[INCOME.table_id], verdict="answerable", missing="")])
CODE = CodeDraft(code='emit([{"part": 1, "status": "answered", "values": {"Revenue": 1288.7}}])', approach="Sum the regions.")
GOOD = SandboxResult(0, False, '{"parts": [{"part": 1, "status": "answered", "values": {"Revenue": 1288.7}}]}', "")


def test_calculate_with_a_swapped_table_resumes_the_same_thread(make_settings, tmp_path) -> None:
    """VC-314, VC-316, VC-319 (thread), VC-320 (metadata) smoke: the run pauses after `select`;
    Calculate with another Candidate table runs the code on that table, in the same thread."""
    # Given: two Candidate tables, the model selecting the first
    answers = [PLAN, SELECTION, CODE, FinalAnswer(text="Net revenue is 1,288.7 USD millions.")]
    deps, model, runner = analyst_deps(make_settings(), tmp_path, answers, [GOOD], entries=[INCOME, REGIONS])

    # When: the run starts with confirmation on
    paused = run_analysis(PLAN.standalone_question, [], deps, True, thread_id="confirm-swap")

    # Then: it waits before any code, offering both Candidate tables with the selection ticked
    request = paused["confirmation_request"]
    assert request["parts"][0]["selected"] == [INCOME.table_id]
    assert {c["table_id"] for c in request["parts"][0]["candidates"]} == {INCOME.table_id, REGIONS.table_id}
    assert not runner.calls and paused["answer_status"] is None

    # When: the user swaps the table and calculates
    final = resume_analysis("confirm-swap", {"action": "calculate", "tables": {1: [REGIONS.table_id]}}, deps)

    # Then: the code ran on the swapped table and the run finished, marked as changed
    assert runner.calls[0]["files"] == sorted(["main.py", f"{REGIONS.table_id}.parquet"])
    assert final["answer_status"] == "answered" and final["confirmation"] == "changed"
    assert "confirmation_request" not in final


def test_cancel_ends_cannot_answer_without_code(make_settings, tmp_path) -> None:
    """VC-317 smoke: Cancel → `cannot_answer`, every part "Cancelled before calculating.", no code."""
    # Given: a run paused at the confirmation
    answers = [PLAN, SELECTION, FinalAnswer(text="Cancelled before calculating.")]
    deps, model, runner = analyst_deps(make_settings(), tmp_path, answers, [], entries=[INCOME, REGIONS])
    run_analysis(PLAN.standalone_question, [], deps, True, thread_id="confirm-cancel")

    # When: the user cancels
    final = resume_analysis("confirm-cancel", {"action": "cancel"}, deps)

    # Then: no code ran and every part carries the cancellation reason
    assert final["answer_status"] == "cannot_answer" and final["confirmation"] == "cancelled"
    assert [o.reason for o in final["part_outcomes"]] == [CANCELLED_REASON]
    assert not runner.calls and final["code_attempts"] == 0
