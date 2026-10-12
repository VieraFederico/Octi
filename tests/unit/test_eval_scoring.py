"""The evaluation's deterministic scoring (spec 03 FR-308 … FR-310; D-108, D-112): three
evaluators read a run's final state, never an LLM (BR-302), and the results file is written from
the scored rows."""

from agents.analyst.schemas import PartOutcome, PartSelection, TableSelection
from eval.scoring import (
    ExpectedValue,
    Question,
    error_row,
    score_run,
    status_correct,
    tables_correct,
    values_correct,
    write_results,
)
from tests.stubs import analyst_catalog_entry as catalog_entry


def question(**overrides) -> Question:
    """A two-table `answered` test question; fields overridable."""
    fields = {
        "id": "q04",
        "question": "What share of ACME's net revenue did R&D expenses represent in 2023?",
        "category": "multi_table",
        "expected_status": "answered",
        "expected_values": [ExpectedValue(name="share", value=7.2, unit="percent")],
        "expected_tables": ["Income summary", "R&D expenses"],
        "expected_answer": "R&D expenses were 7.2 % of net revenue in 2023.",
    }
    return Question(**(fields | overrides))


def final_state(values: dict, verdicts: dict[int, tuple[str, list[str]]], status: str = "answered") -> dict:
    """A fake Analyst final state: per part number a (verdict, table ids); part 1 carries `values`."""
    candidates = [
        catalog_entry(table_id="t-income", name="Income summary"),
        catalog_entry(table_id="t-rd", name="R&D expenses"),
        catalog_entry(table_id="t-staff", name="Headcount"),
    ]
    parts = [PartSelection(part=n, table_ids=ids, verdict=v, missing="" if v == "answerable" else "absent")
             for n, (v, ids) in verdicts.items()]
    outcomes = [PartOutcome(part=1, outcome="answered", values=values)] if values else []
    return {
        "candidates": candidates,
        "selection": TableSelection(parts=parts),
        "part_outcomes": outcomes,
        "answer_status": status,
        "code_attempts": 2,
    }


def test_evaluators_score_a_fake_final_state():
    """VC-308 (smoke): status, values (percent as fraction or percent, 1 % tolerance, "–" for
    `cannot_answer`) and tables (answerable parts only) from a fake final state."""
    # Given: a run that answered with 0.072 using both expected tables, plus an unanswerable part
    state = final_state({"share": 0.072},
                        {1: ("answerable", ["t-income", "t-rd"]), 2: ("missing_data", ["t-staff"])})

    # When / Then: every evaluator passes; the unanswerable part's table is not counted
    assert status_correct(question(), state) is True
    assert values_correct(question(), state) is True
    assert tables_correct(question(), state) is True

    # Then: a value 2 % off fails, and a percent written as 7.2 also matches
    assert values_correct(question(), final_state({"share": 0.0735}, {1: ("answerable", ["t-income"])})) is False
    assert values_correct(question(), final_state({"share": 7.2}, {1: ("answerable", ["t-income"])})) is True

    # Then: a `cannot_answer` question skips values, and expects no Selected table
    nothing = question(expected_status="cannot_answer", expected_values=[], expected_tables=[])
    empty = final_state({}, {1: ("missing_data", ["t-income"])}, status="cannot_answer")
    assert values_correct(nothing, empty) is None
    assert tables_correct(nothing, empty) is True
    assert tables_correct(nothing, final_state({}, {1: ("answerable", ["t-income"])})) is False


def test_results_file_has_header_rows_and_totals(tmp_path):
    """VC-309, VC-310 (smoke): a scored row and an error row are written with the header, the
    listed columns and one totals line per evaluator."""
    # Given: one scored run and one run that raised
    state = final_state({"share": 7.2}, {1: ("answerable", ["t-income", "t-rd"])})
    rows = [
        score_run(question(), state, trace_url="https://example.test/r/1"),
        error_row(question(id="q05"), "SandboxUnavailableError"),
    ]
    header = {"Run date": "2026-10-11 23:00 UTC", "Model": "gpt-test", "Commit": "abc1234",
              "Experiment": "octi-eval-test"}

    # When: the results file is written
    path = tmp_path / "results.md"
    write_results(path, header, rows)
    text = path.read_text(encoding="utf-8")

    # Then: header lines, the column row, both rows (the error with ✗ and its kind) and the totals
    for name, value in header.items():
        assert f"{name}: {value}" in text
    assert "| id | Question | Expected | Actual | Status | Values | Tables | Retries | Trace |" in text
    assert "| q04 |" in text and "[trace](https://example.test/r/1)" in text
    error_line = next(line for line in text.splitlines() if line.startswith("| q05 |"))
    assert error_line.count("✗") == 3 and "SandboxUnavailableError" in error_line
    assert "status_correct: 1/2" in text
    assert "values_correct: 1/2" in text
    assert "tables_correct: 1/2" in text
