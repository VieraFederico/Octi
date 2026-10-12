"""Plain-code decisions of the Analyst: selection, attempts, status, numbers, template (spec 02).

Staged verification (D-118).
"""

import pytest

from agents.analyst.checks import (
    DUPLICATE_PART_FEEDBACK,
    EMPTY_MISSING_FEEDBACK,
    EMPTY_MISSING_REASON,
    EMIT_FEEDBACK,
    EXTRA_PART_FEEDBACK,
    FAILED_PART_REASON,
    MISSING_PART_FEEDBACK,
    NO_TABLE_FEEDBACK,
    NOT_JSON_DETAIL,
    NUMBER_FEEDBACK,
    SILENT_EXIT_FEEDBACK,
    STDERR_TAIL_CHARS,
    TIMEOUT_FEEDBACK,
    UNKNOWN_TABLE_FEEDBACK,
    WRONG_PARTS_EXTRA,
    WRONG_PARTS_FEEDBACK,
    WRONG_PARTS_MISSING,
    WRONG_PARTS_REPEATED,
    check_numbers,
    check_selection,
    classify_attempt,
    merge_status,
    template_answer,
)
from agents.analyst.schemas import (
    AnswerFacts,
    AnswerStatus,
    AttemptCheck,
    EmittedPart,
    PartOutcome,
    PartSelection,
    QueryPlan,
    QuestionPart,
    TableSelection,
    TableSource,
)
from tests.stubs import query_plan

CANDIDATE = "aaaaaaaaaaaaaaaa-p1-t1"


def _selection(*parts: PartSelection) -> TableSelection:
    return TableSelection(parts=list(parts))


def _entry(
    part: int,
    table_ids: list[str],
    verdict: str = "answerable",
    missing: str = "",
) -> PartSelection:
    return PartSelection(part=part, table_ids=table_ids, verdict=verdict, missing=missing)


def _question_part(number: int, text: str = "What was revenue?", **fields: list[str]) -> QuestionPart:
    return QuestionPart(
        number=number,
        text=text,
        entities=fields.get("entities", []),
        metrics=fields.get("metrics", []),
        periods=fields.get("periods", []),
        operations=fields.get("operations", []),
    )


def _facts(
    *,
    question: str = "What was revenue?",
    parts: list[QuestionPart] | None = None,
    outcomes: list[PartOutcome] | None = None,
    approach: str = "",
    tables: list[TableSource] | None = None,
    answer_status: AnswerStatus = "answered",
) -> AnswerFacts:
    return AnswerFacts(
        question=question,
        parts=[_question_part(1)] if parts is None else parts,
        outcomes=[] if outcomes is None else outcomes,
        approach=approach,
        tables=[] if tables is None else tables,
        answer_status=answer_status,
    )


def _emit(line: str, *, prefix: str = "") -> str:
    return f"{prefix}{line}\n"


def test_check_selection_reports_unknown_id_missing_part_and_empty_missing() -> None:
    """VC-211: an unknown id, a missing part and an empty missing yield exactly three sentences."""
    # Given a plan of two parts and a selection that names an unknown table, skips part 2 and
    # leaves `missing` empty on a non-answerable part
    plan = query_plan("What was revenue in 2023?", "What was it in 2022?")
    selection = _selection(_entry(1, ["not-a-table"], verdict="missing_data", missing=""))

    # When the selection is checked
    feedback = check_selection(selection, plan, [CANDIDATE])

    # Then the three sentences are the module constants, in contract order
    assert feedback == [
        UNKNOWN_TABLE_FEEDBACK.format(part=1, table_id="not-a-table"),
        EMPTY_MISSING_FEEDBACK.format(part=1, verdict="missing_data"),
        MISSING_PART_FEEDBACK.format(part=2),
    ]


def test_check_selection_accepts_a_complete_selection() -> None:
    """VC-211: a selection with one good entry per part and only candidate ids has no feedback."""
    # Given every part once, candidate ids only, and `missing` empty solely on an answerable part
    plan = query_plan("What was revenue in 2023?", "What was it in 2022?")
    selection = _selection(
        _entry(1, [CANDIDATE], verdict="answerable", missing="   "),
        _entry(2, [CANDIDATE], verdict="missing_data", missing="2022 is not in the table."),
    )

    # When the selection is checked
    feedback = check_selection(selection, plan, [CANDIDATE])

    # Then it is valid
    assert feedback == []


def test_check_selection_orders_every_problem_kind() -> None:
    """VC-211: unknown ids, extra parts, empty tables and empty missing come before plan-part gaps."""
    # Given one entry that stacks an unknown id, an extra part and a blank missing, then a
    # duplicated answerable part with no table, and plan part 2 absent
    plan = query_plan("What was revenue in 2023?", "What was it in 2022?")
    selection = _selection(
        _entry(9, ["nope", "nope", "also-bad"], verdict="missing_data", missing="  "),
        _entry(1, [], verdict="answerable"),
        _entry(1, [CANDIDATE], verdict="answerable"),
    )

    # When the selection is checked
    feedback = check_selection(selection, plan, [CANDIDATE])

    # Then each problem is one sentence, in the contract's order
    assert feedback == [
        UNKNOWN_TABLE_FEEDBACK.format(part=9, table_id="nope"),
        UNKNOWN_TABLE_FEEDBACK.format(part=9, table_id="also-bad"),
        EXTRA_PART_FEEDBACK.format(part=9),
        EMPTY_MISSING_FEEDBACK.format(part=9, verdict="missing_data"),
        NO_TABLE_FEEDBACK.format(part=1),
        DUPLICATE_PART_FEEDBACK.format(part=1),
        MISSING_PART_FEEDBACK.format(part=2),
    ]


def test_check_selection_reports_a_duplicate_part_once() -> None:
    """VC-211: three entries for one question part produce one duplicate sentence."""
    # Given part 1 three times, each with a candidate table
    plan = query_plan("What was revenue in 2023?")
    selection = _selection(
        _entry(1, [CANDIDATE]),
        _entry(1, [CANDIDATE]),
        _entry(1, [CANDIDATE]),
    )

    # When the selection is checked
    feedback = check_selection(selection, plan, [CANDIDATE])

    # Then the only sentence is the duplicate one
    assert feedback == [DUPLICATE_PART_FEEDBACK.format(part=1)]


def test_check_selection_reports_an_extra_part() -> None:
    """VC-211: an entry whose part is not in the plan is an extra part."""
    # Given the plan's part present and a second entry for part 9
    plan = query_plan("What was revenue in 2023?")
    selection = _selection(_entry(1, [CANDIDATE]), _entry(9, [CANDIDATE]))

    # When the selection is checked
    feedback = check_selection(selection, plan, [CANDIDATE])

    # Then only the extra part is reported
    assert feedback == [EXTRA_PART_FEEDBACK.format(part=9)]


def test_check_selection_reports_an_answerable_part_with_no_table() -> None:
    """VC-211: an answerable part that names no table gets NO_TABLE_FEEDBACK."""
    # Given the only part answerable with an empty table list
    plan = query_plan("What was revenue in 2023?")
    selection = _selection(_entry(1, [], verdict="answerable"))

    # When the selection is checked
    feedback = check_selection(selection, plan, [CANDIDATE])

    # Then the sentence says the part is answerable but names no table
    assert feedback == [NO_TABLE_FEEDBACK.format(part=1)]


def test_check_selection_reports_repeated_extra_parts_as_extra() -> None:
    """VC-211: two entries for a part the plan does not have are two extra sentences."""
    # Given part 1 valid and part 9 twice
    plan = query_plan("What was revenue in 2023?")
    selection = _selection(_entry(1, [CANDIDATE]), _entry(9, [CANDIDATE]), _entry(9, [CANDIDATE]))

    # When the selection is checked
    feedback = check_selection(selection, plan, [CANDIDATE])

    # Then each extra entry is its own sentence
    assert feedback == [EXTRA_PART_FEEDBACK.format(part=9), EXTRA_PART_FEEDBACK.format(part=9)]


def test_check_selection_reports_missing_parts_in_number_order() -> None:
    """VC-211: gaps are reported by part number, whatever order the plan lists them."""
    # Given a plan whose parts are numbered 2 then 1, and an empty selection
    plan = QueryPlan(
        standalone_question="Both parts.",
        parts=[_question_part(2, "Second?"), _question_part(1, "First?")],
        search_phrases=["annual revenue by year"],
    )

    # When the selection is checked
    feedback = check_selection(_selection(), plan, [CANDIDATE])

    # Then part 1 is named before part 2
    assert feedback == [MISSING_PART_FEEDBACK.format(part=1), MISSING_PART_FEEDBACK.format(part=2)]


def test_classify_attempt_uses_the_stderr_tail_when_the_exit_code_is_not_zero() -> None:
    """VC-219: a non-zero exit feeds back exactly the last 2,000 characters of stderr."""
    # Given a failing run whose stderr is longer than the tail
    stderr = "HEAD" + ("x" * 5_000)

    # When the attempt is classified
    result = classify_attempt(1, False, "ignored\n", stderr, [1], 30)

    # Then the failure is a Python error and the feedback is that tail, with no parsed parts
    assert result == AttemptCheck(
        failure="python_error",
        feedback=stderr[-STDERR_TAIL_CHARS:],
        emitted=[],
    )
    assert len(result.feedback) == STDERR_TAIL_CHARS


def test_classify_attempt_keeps_a_short_stderr_message() -> None:
    """VC-219: a short stderr is the whole Python-error feedback, not a trimmed copy."""
    # Given a failing run with a one-line traceback
    stderr = "NameError: name 'rows' is not defined\n"

    # When the attempt is classified
    result = classify_attempt(1, False, "", stderr, [1], 30)

    # Then the feedback is that stderr unchanged
    assert result.failure == "python_error"
    assert result.feedback == stderr
    assert result.emitted == []


def test_classify_attempt_names_a_silent_non_zero_exit() -> None:
    """VC-219: a non-zero exit with no error text uses the silent-exit sentence."""
    # Given exit 137 and an empty stderr
    # When the attempt is classified
    result = classify_attempt(137, False, "", "", [1], 30)

    # Then the feedback names that exit code
    assert result == AttemptCheck(
        failure="python_error",
        feedback=SILENT_EXIT_FEEDBACK.format(exit_code=137),
        emitted=[],
    )


def test_classify_attempt_treats_whitespace_stderr_as_silent() -> None:
    """VC-219: stderr that prints no error message is the silent-exit sentence."""
    # Given a non-zero exit whose stderr is only whitespace
    # When the attempt is classified
    result = classify_attempt(1, False, "", " \n\t", [1], 30)

    # Then there is no traceback to pass on
    assert result.feedback == SILENT_EXIT_FEEDBACK.format(exit_code=1)


def test_classify_attempt_reports_a_timeout_ahead_of_a_non_zero_exit() -> None:
    """VC-219: a timeout names N seconds and wins over a non-zero exit code."""
    # Given a run that timed out, with a failing exit code and a valid emit line
    stdout = _emit('{"parts": [{"part": 1, "status": "answered", "values": {"revenue": 1}}]}')

    # When the attempt is classified
    result = classify_attempt(1, True, stdout, "killed\n", [1], 30)

    # Then the only failure is the timeout sentence for those seconds
    assert result == AttemptCheck(
        failure="timeout",
        feedback=TIMEOUT_FEEDBACK.format(seconds=30),
        emitted=[],
    )


@pytest.mark.parametrize(
    "stdout",
    ["", "not json\n", "[]\n", "123\n", '{"parts": null}\n', '{"parts": {}}\n', '{"other": []}\n'],
)
def test_classify_attempt_rejects_a_last_line_that_is_not_an_emit_object(stdout: str) -> None:
    """VC-219: not JSON, or JSON without a parts list, asks for one emit call."""
    # Given a successful exit whose last line is not an object with a parts list
    # When the attempt is classified
    result = classify_attempt(0, False, stdout, "", [1], 30)

    # Then the feedback is the emit sentence plus the not-JSON detail, without the line's text
    assert result == AttemptCheck(
        failure="invalid_output",
        feedback=f"{EMIT_FEEDBACK} {NOT_JSON_DETAIL}",
        emitted=[],
    )
    assert "not json" not in result.feedback


def test_classify_attempt_reports_a_schema_error_without_the_input_value() -> None:
    """VC-219: a parts list that fails the schema adds the loc and message, never the input."""
    # Given a last line whose status is not answered or missing
    stdout = _emit('{"parts": [{"part": 1, "status": "LEAKED_STATUS"}]}')

    # When the attempt is classified
    result = classify_attempt(0, False, stdout, "", [1], 30)

    # Then the detail names the field and the allowed statuses, and not the bad status text
    assert result.failure == "invalid_output"
    assert result.emitted == []
    assert result.feedback == (
        f"{EMIT_FEEDBACK} 0.status: Input should be 'answered' or 'missing'"
    )
    assert "LEAKED_STATUS" not in result.feedback


def test_classify_attempt_joins_schema_errors_and_hides_input_values() -> None:
    """VC-219: several schema errors are joined, and a bad value is not copied into the feedback."""
    # Given a part missing its number and a value that is not a number or text
    missing_fields = _emit('{"parts": [{"status": "LEAKED_STATUS"}]}')
    bad_value = _emit('{"parts": [{"part": 1, "status": "answered", "values": {"revenue": null}}]}')

    # When each attempt is classified
    missing = classify_attempt(0, False, missing_fields, "", [1], 30)
    value = classify_attempt(0, False, bad_value, "", [1], 30)

    # Then the errors are loc: message, separated by "; ", with no input value
    assert missing.feedback == (
        f"{EMIT_FEEDBACK} 0.part: Field required; "
        "0.status: Input should be 'answered' or 'missing'"
    )
    assert "LEAKED_STATUS" not in missing.feedback
    assert value.feedback == (
        f"{EMIT_FEEDBACK} "
        "0.values.revenue.float: Input should be a valid number; "
        "0.values.revenue.int: Input should be a valid integer; "
        "0.values.revenue.str: Input should be a valid string"
    )
    assert "null" not in value.feedback


def test_classify_attempt_lists_missing_extra_and_repeated_parts() -> None:
    """VC-219: emitted parts that are not the answerable parts name missing, extra and repeats."""
    # Given answerable parts 2 and 1, and an emit line that repeats 2 and adds 9
    stdout = _emit(
        '{"parts": ['
        '{"part": 2, "status": "answered", "values": {"revenue": 1}},'
        '{"part": 2, "status": "missing", "missing": "again"},'
        '{"part": 9, "status": "answered", "values": {}}'
        "]}"
    )

    # When the attempt is classified
    result = classify_attempt(0, False, stdout, "", [2, 1], 30)

    # Then the feedback lists the expected parts in order and only the problems that occurred
    assert result == AttemptCheck(
        failure="wrong_parts",
        feedback=" ".join(
            [
                WRONG_PARTS_FEEDBACK.format(expected="1, 2"),
                WRONG_PARTS_MISSING.format(parts="1"),
                WRONG_PARTS_EXTRA.format(parts="9"),
                WRONG_PARTS_REPEATED.format(parts="2"),
            ]
        ),
        emitted=[],
    )


def test_classify_attempt_omits_empty_wrong_part_clauses() -> None:
    """VC-219: a wrong-parts sentence names only the problem that happened."""
    # Given part 1 emitted once and an extra part 3 beside it
    stdout = _emit(
        '{"parts": ['
        '{"part": 1, "status": "answered", "values": {}},'
        '{"part": 3, "status": "answered", "values": {}}'
        "]}"
    )

    # When the attempt is classified
    result = classify_attempt(0, False, stdout, "", [1], 30)

    # Then missing and repeated clauses are absent
    assert result.failure == "wrong_parts"
    assert result.feedback == " ".join(
        [WRONG_PARTS_FEEDBACK.format(expected="1"), WRONG_PARTS_EXTRA.format(parts="3")]
    )
    assert "Missing parts" not in result.feedback
    assert "Repeated parts" not in result.feedback


def test_classify_attempt_accepts_a_part_emitted_missing() -> None:
    """VC-219: a part emitted missing is not a failure, and lines before the JSON are ignored."""
    # Given a log line, then one missing part for the only answerable part
    stdout = _emit(
        '{"parts": [{"part": 1, "status": "missing", "missing": "No row for 2024."}]}',
        prefix="not json and not a parts list\n",
    )

    # When the attempt is classified
    result = classify_attempt(0, False, stdout, "", [1], 30)

    # Then the attempt stands, with that part parsed
    assert result == AttemptCheck(
        failure=None,
        feedback="",
        emitted=[EmittedPart(part=1, status="missing", missing="No row for 2024.")],
    )


def test_classify_attempt_ignores_output_before_the_last_json_line() -> None:
    """VC-219: only the last non-blank line is the emit line; earlier JSON is not used."""
    # Given a valid emit line followed by another non-blank line
    stdout = '{"parts": [{"part": 1, "status": "answered", "values": {}}]}\ndone\n'

    # When the attempt is classified
    result = classify_attempt(0, False, stdout, "", [1], 30)

    # Then the last line is what is classified
    assert result.failure == "invalid_output"
    assert result.feedback == f"{EMIT_FEEDBACK} {NOT_JSON_DETAIL}"


def test_classify_attempt_returns_parsed_parts_when_the_emit_line_matches() -> None:
    """VC-219: a matching emit line returns the parts, in emit order, and no failure."""
    # Given both answerable parts, emitted out of number order, with an extra key on the object
    stdout = _emit(
        '{"note": "ignore", "parts": ['
        '{"part": 2, "status": "answered", "values": {"cost": 12}, "note": "x"},'
        '{"part": 1, "status": "answered", "values": {"revenue": 1288.7}}'
        "]}\n\n"
    )

    # When the attempt is classified
    result = classify_attempt(0, False, stdout, "", {1, 2}, 30)

    # Then the parts are kept and the extra key is not
    assert result.failure is None
    assert result.feedback == ""
    assert result.emitted == [
        EmittedPart(part=2, status="answered", values={"cost": 12}),
        EmittedPart(part=1, status="answered", values={"revenue": 1288.7}),
    ]


def test_merge_status_keeps_values_when_the_part_was_answered() -> None:
    """VC-222: an answerable part the code answered stays answered, with its values."""
    # Given an answerable part and an answered emit entry
    selection = _selection(_entry(1, [CANDIDATE]))
    emitted = [EmittedPart(part=1, status="answered", values={"revenue": 1288.7, "note": "final"})]

    # When the status is merged
    outcomes, status = merge_status(selection, emitted, failed=False)

    # Then the value is kept and the run is answered
    assert outcomes == [
        PartOutcome(part=1, outcome="answered", values={"revenue": 1288.7, "note": "final"}, reason="")
    ]
    assert status == "answered"


def test_merge_status_uses_the_code_reason_when_the_part_was_emitted_missing() -> None:
    """VC-222: an answerable part the code marks missing keeps the code's reason, not its values."""
    # Given an answered-looking value on a part the code emitted as missing
    selection = _selection(_entry(1, [CANDIDATE]))
    emitted = [EmittedPart(part=1, status="missing", values={"revenue": 1288.7}, missing="No row for 2024.")]

    # When the status is merged
    outcomes, status = merge_status(selection, emitted, failed=False)

    # Then the outcome is missing for that reason, with no value
    assert outcomes == [PartOutcome(part=1, outcome="missing", values={}, reason="No row for 2024.")]
    assert status == "cannot_answer"


def test_merge_status_fills_a_blank_emitted_reason() -> None:
    """VC-222: a missing emit entry with a blank reason gets the empty-missing sentence."""
    # Given the code said missing and left the reason blank
    selection = _selection(_entry(1, [CANDIDATE]))
    emitted = [EmittedPart(part=1, status="missing", values={"revenue": 5}, missing="  ")]

    # When the status is merged
    outcomes, status = merge_status(selection, emitted, failed=False)

    # Then the reason is the module sentence and the value is dropped
    assert outcomes == [PartOutcome(part=1, outcome="missing", values={}, reason=EMPTY_MISSING_REASON)]
    assert status == "cannot_answer"


def test_merge_status_uses_the_selection_reason_when_the_part_is_not_answerable() -> None:
    """VC-222: a part that is not answerable is missing for the selection's reason."""
    # Given a missing-data part and an ambiguous part, even if code ran and the attempts failed
    selection = _selection(
        _entry(2, [CANDIDATE], verdict="missing_data", missing="No 2024 column."),
        _entry(1, [CANDIDATE], verdict="ambiguous", missing="Two revenue columns."),
    )
    emitted = [EmittedPart(part=1, status="answered", values={"revenue": 5})]

    # When the status is merged
    outcomes, status = merge_status(selection, emitted, failed=True)

    # Then both are missing, in part order, with no computed value
    assert outcomes == [
        PartOutcome(part=1, outcome="missing", values={}, reason="Two revenue columns."),
        PartOutcome(part=2, outcome="missing", values={}, reason="No 2024 column."),
    ]
    assert status == "cannot_answer"


def test_merge_status_fails_an_answerable_part_when_the_attempts_are_used_up() -> None:
    """VC-222: an answerable part is failed, without values, when the attempts were used up."""
    # Given an answerable part and a last emit that did produce a value
    selection = _selection(_entry(1, [CANDIDATE]))
    emitted = [EmittedPart(part=1, status="answered", values={"revenue": 1288.7})]

    # When the merge is told the attempts failed
    outcomes, status = merge_status(selection, emitted, failed=True)

    # Then the part is failed with the fixed reason
    assert outcomes == [PartOutcome(part=1, outcome="failed", values={}, reason=FAILED_PART_REASON)]
    assert status == "cannot_answer"


def test_merge_status_fails_an_answerable_part_with_no_emitted_entry() -> None:
    """VC-222: an answerable part with no emit entry is failed."""
    # Given an answerable part and an empty emit list, without the failed flag
    selection = _selection(_entry(1, [CANDIDATE]))

    # When the status is merged
    outcomes, status = merge_status(selection, [], failed=False)

    # Then the part is still failed
    assert outcomes == [PartOutcome(part=1, outcome="failed", values={}, reason=FAILED_PART_REASON)]
    assert status == "cannot_answer"


def test_merge_status_is_answered_when_every_part_is_answered() -> None:
    """VC-222: every part answered makes the Answer status answered."""
    # Given two answerable parts, both emitted answered
    selection = _selection(_entry(1, [CANDIDATE]), _entry(2, [CANDIDATE]))
    emitted = [
        EmittedPart(part=1, status="answered", values={"revenue": 1}),
        EmittedPart(part=2, status="answered", values={"revenue": 2}),
    ]

    # When the status is merged
    outcomes, status = merge_status(selection, emitted, failed=False)

    # Then both values are kept and the status is answered
    assert [outcome.outcome for outcome in outcomes] == ["answered", "answered"]
    assert [outcome.values for outcome in outcomes] == [{"revenue": 1}, {"revenue": 2}]
    assert status == "answered"


def test_merge_status_is_partial_when_one_of_two_parts_is_answered() -> None:
    """VC-222: one answered part of two is partial, values stay only on the answered one."""
    # Given part 2 answered and part 1 not answerable, listed out of order
    selection = _selection(
        _entry(2, [CANDIDATE], verdict="answerable"),
        _entry(1, [CANDIDATE], verdict="missing_data", missing="No 2022 column."),
    )
    emitted = [EmittedPart(part=2, status="answered", values={"revenue": 1288.7})]

    # When the status is merged
    outcomes, status = merge_status(selection, emitted, failed=False)

    # Then the outcomes are in part order and only the answered one carries a value
    assert outcomes == [
        PartOutcome(part=1, outcome="missing", values={}, reason="No 2022 column."),
        PartOutcome(part=2, outcome="answered", values={"revenue": 1288.7}, reason=""),
    ]
    assert status == "partial"


def test_merge_status_is_cannot_answer_when_no_part_is_answered() -> None:
    """VC-222: when no part is answered the status is cannot_answer."""
    # Given one part not answerable and one answerable part whose attempts failed
    selection = _selection(
        _entry(1, [CANDIDATE], verdict="missing_data", missing="No 2024 column."),
        _entry(2, [CANDIDATE]),
    )

    # When the status is merged
    outcomes, status = merge_status(selection, [], failed=True)

    # Then nothing was answered
    assert [outcome.outcome for outcome in outcomes] == ["missing", "failed"]
    assert status == "cannot_answer"


def test_check_numbers_accepts_thousands_separators_for_a_computed_value() -> None:
    """VC-226: 1,288.7 passes for a computed 1288.7."""
    # Given an answered revenue of 1288.7
    facts = _facts(outcomes=[PartOutcome(part=1, outcome="answered", values={"revenue": 1288.7})])

    # When the answer writes it with a thousands separator
    feedback = check_numbers("Revenue was 1,288.7.", facts)

    # Then the number is backed
    assert feedback == []


def test_check_numbers_reports_an_invented_number() -> None:
    """VC-226: an invented 1,300 is reported with the number-check sentence."""
    # Given an answered revenue of 1288.7
    facts = _facts(outcomes=[PartOutcome(part=1, outcome="answered", values={"revenue": 1288.7})])

    # When the answer invents 1,300 beside the real figure
    feedback = check_numbers("Revenue was 1,288.7, not 1,300.", facts)

    # Then only the invented number is reported, as written
    assert feedback == [NUMBER_FEEDBACK.format(number="1,300")]


def test_check_numbers_accepts_a_spanish_thousands_form() -> None:
    """VC-226: Spanish 1.288,7 passes for a computed 1288.7."""
    # Given an answered revenue of 1288.7
    facts = _facts(outcomes=[PartOutcome(part=1, outcome="answered", values={"revenue": 1288.7})])

    # When the answer uses a dot for thousands and a comma for the decimal
    feedback = check_numbers("El ingreso fue 1.288,7.", facts)

    # Then the number is backed
    assert feedback == []


def test_check_numbers_accepts_rounding_to_the_shown_precision() -> None:
    """VC-226: 1,289 passes for 1288.7; 1,290 is beyond half a unit and is reported."""
    # Given an answered revenue of 1288.7
    facts = _facts(outcomes=[PartOutcome(part=1, outcome="answered", values={"revenue": 1288.7})])

    # When the answer rounds to the nearest whole number, and when it rounds one step further
    rounded = check_numbers("About 1,289.", facts)
    too_far = check_numbers("About 1,290.", facts)

    # Then only the nearer rounding passes
    assert rounded == []
    assert too_far == [NUMBER_FEEDBACK.format(number="1,290")]


def test_check_numbers_accepts_a_scale_word() -> None:
    """VC-226: 1.29 billion passes for a computed 1288.7."""
    # Given an answered value of 1288.7
    facts = _facts(outcomes=[PartOutcome(part=1, outcome="answered", values={"revenue": 1288.7})])

    # When the answer writes that magnitude with a scale word
    feedback = check_numbers("Revenue was 1.29 billion.", facts)

    # Then the scaled reading is backed
    assert feedback == []


def test_check_numbers_accepts_a_percent_for_a_fraction() -> None:
    """VC-226: 12.5% passes for a computed 0.125."""
    # Given an answered fraction 0.125
    facts = _facts(outcomes=[PartOutcome(part=1, outcome="answered", values={"share": 0.125})])

    # When the answer writes it as a percent
    feedback = check_numbers("The share was 12.5%.", facts)

    # Then the percent is backed
    assert feedback == []


@pytest.mark.parametrize(
    "word",
    [
        "thousand",
        "thousands",
        "million",
        "millions",
        "billion",
        "billions",
        "k",
        "M",
        "bn",
        "mil",
        "millón",
        "millones",
        "miles",
    ],
)
def test_check_numbers_accepts_each_scale_word(word: str) -> None:
    """VC-226: a scale word allows the computed value times a power of 1,000."""
    # Given a computed 5,000,000, which is 5 times 1,000 squared. 5 is not a part number.
    facts = _facts(outcomes=[PartOutcome(part=1, outcome="answered", values={"n": 5_000_000})])

    # When the answer writes 5 followed by that scale word
    feedback = check_numbers(f"The figure is 5 {word}.", facts)

    # Then the number is backed
    assert feedback == []


@pytest.mark.parametrize("phrase", ["12.5%", "12.5 percent", "12.5 por ciento", "12,5 por ciento"])
def test_check_numbers_accepts_percent_phrases(phrase: str) -> None:
    """VC-226: percent, por ciento and a trailing % match a fraction times 100."""
    # Given a computed fraction 0.125
    facts = _facts(outcomes=[PartOutcome(part=1, outcome="answered", values={"share": 0.125})])

    # When the answer writes one of the percent forms
    feedback = check_numbers(f"The share was {phrase}.", facts)

    # Then the number is backed
    assert feedback == []


def test_check_numbers_requires_the_scale_word_to_follow_the_number() -> None:
    """VC-226: a scale word later in the sentence does not scale an earlier number."""
    # Given a computed 1288.7
    facts = _facts(outcomes=[PartOutcome(part=1, outcome="answered", values={"revenue": 1288.7})])

    # When 1.29 is not immediately followed by the scale word
    feedback = check_numbers("1.29 is not written as a billion.", facts)

    # Then 1.29 is not backed
    assert feedback == [NUMBER_FEEDBACK.format(number="1.29")]


def test_check_numbers_accepts_years_pages_part_numbers_and_numbers_written_in_the_facts() -> None:
    """VC-226: years, pages, part numbers and numbers written in the facts pass."""
    # Given facts that mention years, a page, a part number and other figures only in text
    facts = _facts(
        question="What happened in 2023?",
        parts=[
            _question_part(
                2,
                "How did the top 3 change?",
                entities=["group 6"],
                metrics=["batch 12"],
                periods=["2022"],
                operations=["step 9"],
            )
        ],
        outcomes=[PartOutcome(part=2, outcome="missing", values={"note": "row 5"}, reason="No data for 2024.")],
        approach="Used method 8.",
        tables=[TableSource(name="Summary 88", source_file="notes-61.pdf", pages=[14])],
        answer_status="cannot_answer",
    )
    text = "See 2023, top 3, group 6, batch 12, 2022, step 9, row 5, 2024, method 8, summary 88, file 61, page 14 and part 2."

    # When the answer repeats those figures and invents one more
    feedback = check_numbers(text + " Not 7,777.", facts)

    # Then only the invented number is reported
    assert feedback == [NUMBER_FEEDBACK.format(number="7,777")]


def test_check_numbers_reports_repeated_offenders_once_in_order() -> None:
    """VC-226: the same invented number is reported once, in the order it first appears."""
    # Given no computed value
    facts = _facts()

    # When two invented numbers appear, the first of them twice
    feedback = check_numbers("7,777 and 8,888 and 7,777.", facts)

    # Then each offending writing appears once, in that order
    assert feedback == [
        NUMBER_FEEDBACK.format(number="7,777"),
        NUMBER_FEEDBACK.format(number="8,888"),
    ]


def test_check_numbers_uses_the_absolute_value_of_a_computed_number() -> None:
    """VC-226: a negative computed value backs the same figure written without a sign."""
    # Given a computed -1288.7
    facts = _facts(outcomes=[PartOutcome(part=1, outcome="answered", values={"revenue": -1288.7})])

    # When the answer writes the magnitude
    feedback = check_numbers("The change was 1,288.7.", facts)

    # Then the number is backed
    assert feedback == []


def test_check_numbers_ignores_numeric_values_on_a_part_that_was_not_answered() -> None:
    """VC-226: a value kept on a missing part does not back a number in the answer."""
    # Given 1288.7 stored on a missing outcome
    facts = _facts(
        outcomes=[PartOutcome(part=1, outcome="missing", values={"revenue": 1288.7}, reason="No column.")]
    )

    # When the answer states that figure
    feedback = check_numbers("Revenue was 1,288.7.", facts)

    # Then it is not a computed result
    assert feedback == [NUMBER_FEEDBACK.format(number="1,288.7")]


def test_template_answer_states_results_method_sources_and_unanswered_parts() -> None:
    """VC-226: the template states results, the method, the sources and each unanswered part."""
    # Given one answered part, a method, two sources and two unanswered parts, listed out of order
    facts = _facts(
        parts=[_question_part(1), _question_part(2), _question_part(3)],
        outcomes=[
            PartOutcome(part=3, outcome="failed", reason=FAILED_PART_REASON),
            PartOutcome(
                part=1,
                outcome="answered",
                values={
                    "revenue": 1288.7,
                    "cost": 12887,
                    "ratio": 1.23456789,
                    "units": 1000.0,
                    "delta": -50.5,
                },
            ),
            PartOutcome(part=2, outcome="missing", reason="The year 2024 is not in the table"),
        ],
        approach="Summed the revenue column",
        tables=[
            TableSource(name="Income statement", source_file="acme.pdf", pages=[3]),
            TableSource(name="Balance sheet", source_file="acme.pdf", pages=[4, 5]),
        ],
        answer_status="partial",
    )

    # When the template answer is built
    text = template_answer(facts)

    # Then the lines are the results, the method, the sources and the unanswered parts
    assert text == (
        "Question 1: revenue = 1,288.7; cost = 12,887; ratio = 1.2346; units = 1,000; delta = -50.5. "
        "Method: Summed the revenue column. "
        "Sources: Income statement (acme.pdf, page 3); Balance sheet (acme.pdf, pages 4, 5). "
        "Question 2 could not be answered: The year 2024 is not in the table. "
        "Question 3 could not be answered: I couldn't compute this part."
    )
    assert check_numbers(text, facts) == []


def test_template_answer_numbers_pass_the_number_check() -> None:
    """VC-226: every number in the template answer is backed by the same facts."""
    # Given answered values, a method that cites a year, a source page and an unanswered reason
    facts = _facts(
        parts=[_question_part(1, "What was revenue in 2023?"), _question_part(2)],
        outcomes=[
            PartOutcome(part=1, outcome="answered", values={"revenue": 1288.7}),
            PartOutcome(part=2, outcome="missing", reason="No column for 2022."),
        ],
        approach="Read the 2023 column.",
        tables=[TableSource(name="Income statement", source_file="acme.pdf", pages=[3])],
        answer_status="partial",
    )

    # When the template is checked against those facts
    feedback = check_numbers(template_answer(facts), facts)

    # Then no number is left over
    assert feedback == []


def test_value_labels_count_as_facts() -> None:
    """VC-226 (S02-D-005): a number inside a computed value's label is backed, so the template passes."""
    # Given an answered part whose label holds a year that appears nowhere else in the facts
    facts = _facts(
        parts=[_question_part(1, "What was revenue last year?")],
        outcomes=[PartOutcome(part=1, outcome="answered", values={"Revenue 2023 (USD millions)": 1288.7})],
        answer_status="answered",
    )

    # When the template answer is checked against those facts
    feedback = check_numbers(template_answer(facts), facts)

    # Then the year in the label is not reported
    assert feedback == []


def test_template_answer_omits_the_method_without_an_answered_part() -> None:
    """VC-226: the method and the sources appear only when the facts have them."""
    # Given a missing part, an approach, and no selected table
    facts = _facts(
        outcomes=[PartOutcome(part=1, outcome="missing", reason="No 2024 column.")],
        approach="Summed the column.",
        answer_status="cannot_answer",
    )

    # When the template answer is built
    text = template_answer(facts)

    # Then the unanswered part is the whole answer
    assert text == "Question 1 could not be answered: No 2024 column."


def test_template_answer_does_not_repeat_a_period() -> None:
    """VC-226: a method or a reason that already ends with a period keeps a single period."""
    # Given an approach and a reason that already end with a period
    facts = _facts(
        parts=[_question_part(1), _question_part(2)],
        outcomes=[
            PartOutcome(part=1, outcome="answered", values={"revenue": 10}),
            PartOutcome(part=2, outcome="missing", reason="No 2024 column."),
        ],
        approach="Summed the column.",
        answer_status="partial",
    )

    # When the template answer is built
    text = template_answer(facts)

    # Then neither sentence grows a second period
    assert text == (
        "Question 1: revenue = 10. "
        "Method: Summed the column. "
        "Question 2 could not be answered: No 2024 column."
    )


def test_template_answer_shows_no_value_when_the_status_is_cannot_answer() -> None:
    """VC-225: a cannot_answer template shows no computed value, even if an outcome carries one."""
    # Given cannot_answer facts whose outcomes still hold a distinctive value
    facts = _facts(
        parts=[_question_part(1), _question_part(2)],
        outcomes=[
            PartOutcome(part=1, outcome="answered", values={"revenue": 987654.25}, reason=""),
            PartOutcome(part=2, outcome="missing", values={"cost": 987654.25}, reason="The year is absent"),
        ],
        approach="Read the cell.",
        tables=[TableSource(name="Income statement", source_file="acme.pdf", pages=[3])],
        answer_status="cannot_answer",
    )

    # When the template answer is built
    text = template_answer(facts)

    # Then the value is absent and the unanswered reason remains
    assert "987,654.25" not in text
    assert "987654.25" not in text
    assert "revenue" not in text
    assert "The year is absent." in text
