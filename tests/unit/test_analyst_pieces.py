"""The Analyst's pure pieces fit together: prompt few-shot → prelude → checks (spec 02 Iteration 1 seams)."""

import contextlib
import io

import pandas as pd

from agents.analyst.checks import check_numbers, classify_attempt, merge_status, template_answer
from agents.analyst.prelude import make_aliases, prelude_source
from agents.analyst.prompts import CODE_EXAMPLE
from agents.analyst.schemas import AnswerFacts, TableSource


def test_code_example_aliases_are_the_ones_octi_derives() -> None:
    """FR-215 / S02-D-006: the few-shot shows the alias `make_aliases` gives its table."""
    assert make_aliases(CODE_EXAMPLE.selected) == CODE_EXAMPLE.aliases


def test_code_example_runs_through_the_prelude_and_the_checks() -> None:
    """VC-223, VC-219, VC-222, VC-226 (seam): the few-shot code's emit line is classified, merged and answered."""
    # Given the prelude with the example's table built in memory, as the sandbox would load it
    namespace: dict[str, object] = {}
    exec(prelude_source({}), namespace)  # noqa: S102 - Octi's own prelude, never generated code (BR-204)
    alias = next(iter(CODE_EXAMPLE.aliases))
    namespace["tables"] = {
        alias: pd.DataFrame({"Route": ["North", "South"], "2022": [1240.0, 410.0], "2023": [1315.5, None]})
    }
    # When the example's code runs and prints its result
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        exec(CODE_EXAMPLE.answer.code, namespace)  # noqa: S102 - the example is Octi's own text
    check = classify_attempt(0, False, stdout.getvalue(), "", answerable_parts=[1, 2], timeout_seconds=30)
    outcomes, status = merge_status(CODE_EXAMPLE.selection, check.emitted, failed=False)
    # Then the attempt is valid, part 1 is answered, part 2 is missing, the status is partial
    assert check.failure is None
    assert [outcome.outcome for outcome in outcomes] == ["answered", "missing"]
    assert status == "partial"
    # And the template answer built from those facts passes the number check
    table = CODE_EXAMPLE.selected[0]
    facts = AnswerFacts(
        question=CODE_EXAMPLE.plan.standalone_question,
        parts=CODE_EXAMPLE.plan.parts,
        outcomes=outcomes,
        approach=CODE_EXAMPLE.answer.approach,
        tables=[TableSource(name=table.name, source_file=table.source_file, pages=table.pages)],
        answer_status=status,
    )
    assert check_numbers(template_answer(facts), facts) == []
