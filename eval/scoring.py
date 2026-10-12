"""Test questions and their deterministic scoring.

- `load_questions` reads `eval/questions.yaml` into `Question` models and rejects a malformed file.
- Three evaluators read an Analyst run's final state and return `True` / `False`, or `None` when the
  check does not apply: `status_correct`, `values_correct`, `tables_correct`. They are plain code, so
  no model grades another model.
- `score_run` and `error_row` turn a run (or its error) into a `ResultRow`; `write_results` writes
  `eval/results.md` from the rows.

The final state is read through spec 02's Analyst state fields: `answer_status`, `part_outcomes`
(`PartOutcome`), `selection` (`TableSelection`), `candidates` (`CatalogEntry`) and `code_attempts`.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from agents.analyst.schemas import AnswerStatus

CATEGORIES = (
    "single_table",
    "scale_conversion",
    "spanish",
    "multi_table",
    "multi_table_cross_pdf",
    "no_related_table",
    "missing_year",
    "partial",
    "missing_comparison",
    "ambiguous",
)
Category = Literal[
    "single_table",
    "scale_conversion",
    "spanish",
    "multi_table",
    "multi_table_cross_pdf",
    "no_related_table",
    "missing_year",
    "partial",
    "missing_comparison",
    "ambiguous",
]

RELATIVE_TOLERANCE = 0.01
ZERO_TOLERANCE = 0.001
PASS, FAIL, NOT_APPLICABLE = "✓", "✗", "–"
COLUMNS = ("id", "Question", "Expected", "Actual", "Status", "Values", "Tables", "Retries", "Trace")
EVALUATORS = ("status_correct", "values_correct", "tables_correct")


class ExpectedValue(BaseModel):
    """One value the answer must contain; `unit: percent` also accepts the value as a fraction."""

    name: str
    value: float
    unit: Literal["percent"] | None = None


class Question(BaseModel):
    """One entry of `eval/questions.yaml`."""

    id: str = Field(pattern=r"^q\d{2}$")
    question: str = Field(min_length=1)
    category: Category
    expected_status: AnswerStatus
    expected_values: list[ExpectedValue]
    expected_tables: list[str]
    expected_answer: str = Field(min_length=1)

    @model_validator(mode="after")
    def _no_values_when_unanswerable(self) -> "Question":
        if self.expected_status == "cannot_answer" and self.expected_values:
            raise ValueError("a cannot_answer question expects no values")
        return self


def load_questions(path: Path) -> list[Question]:
    """The questions of a YAML file, validated; raises `ValueError` on a malformed file or repeated id."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{path.name} must hold a list of questions")
    questions = [Question.model_validate(entry) for entry in raw]
    ids = [q.id for q in questions]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{path.name} repeats a question id")
    return questions


# --- Evaluators ----------------------------------------------------------------------------------


def status_correct(question: Question, state: Mapping[str, Any]) -> bool:
    """The run's Answer status equals the expected one."""
    return state.get("answer_status") == question.expected_status


def _matches(expected: ExpectedValue, computed: float) -> bool:
    targets = [expected.value, expected.value / 100] if expected.unit == "percent" else [expected.value]
    for target in targets:
        if target == 0:
            if abs(computed) <= ZERO_TOLERANCE:
                return True
        elif math.isclose(computed, target, rel_tol=RELATIVE_TOLERANCE):
            return True
    return False


def _answered_numbers(state: Mapping[str, Any]) -> list[float]:
    numbers = []
    for outcome in state.get("part_outcomes") or []:
        if outcome.outcome != "answered":
            continue
        numbers += [float(v) for v in outcome.values.values() if isinstance(v, int | float) and not isinstance(v, bool)]
    return numbers


def values_correct(question: Question, state: Mapping[str, Any]) -> bool | None:
    """Every expected value matches some value of an answered part; `None` for `cannot_answer`."""
    if question.expected_status == "cannot_answer":
        return None
    numbers = _answered_numbers(state)
    return all(any(_matches(expected, n) for n in numbers) for expected in question.expected_values)


def selected_table_names(state: Mapping[str, Any]) -> set[str]:
    """The Table names of the answerable Question parts' tables (the Selected tables for scoring)."""
    selection = state.get("selection")
    if selection is None:
        return set()
    names = {entry.table_id: entry.name for entry in state.get("candidates") or []}
    ids = {table_id for part in selection.parts if part.verdict == "answerable" for table_id in part.table_ids}
    return {names.get(table_id, table_id) for table_id in ids}


def tables_correct(question: Question, state: Mapping[str, Any]) -> bool:
    """Every expected Table is selected; an empty expectation is correct only when none is selected."""
    selected = selected_table_names(state)
    if not question.expected_tables:
        return not selected
    return set(question.expected_tables) <= selected


# --- Result rows and the results file ------------------------------------------------------------


@dataclass(frozen=True)
class ResultRow:
    """One question's line in `eval/results.md`; marks are `True` / `False` / `None` (not applicable)."""

    id: str
    question: str
    expected: str
    actual: str
    status: bool | None
    values: bool | None
    tables: bool | None
    retries: int | None
    trace: str = ""
    error: str = ""

    def marks(self) -> dict[str, bool | None]:
        return dict(zip(EVALUATORS, (self.status, self.values, self.tables), strict=True))


def score_run(question: Question, state: Mapping[str, Any], trace_url: str = "") -> ResultRow:
    """The scored row of a run that finished."""
    attempts = int(state.get("code_attempts") or 0)
    return ResultRow(
        id=question.id,
        question=question.question,
        expected=question.expected_status,
        actual=str(state.get("answer_status") or ""),
        status=status_correct(question, state),
        values=values_correct(question, state),
        tables=tables_correct(question, state),
        retries=max(attempts - 1, 0),
        trace=trace_url,
    )


def error_row(question: Question, error_kind: str, trace_url: str = "") -> ResultRow:
    """The row of a run that raised: every check failed, the error kind noted."""
    return ResultRow(
        id=question.id,
        question=question.question,
        expected=question.expected_status,
        actual=f"error: {error_kind}",
        status=False,
        values=False,
        tables=False,
        retries=None,
        trace=trace_url,
        error=error_kind,
    )


def _mark(value: bool | None) -> str:
    return NOT_APPLICABLE if value is None else PASS if value else FAIL


def _cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def _row_line(row: ResultRow) -> str:
    cells = [
        row.id,
        _cell(row.question),
        row.expected,
        _cell(row.actual),
        _mark(row.status),
        _mark(row.values),
        _mark(row.tables),
        "–" if row.retries is None else str(row.retries),
        f"[trace]({row.trace})" if row.trace else "–",
    ]
    return "| " + " | ".join(cells) + " |"


def totals(rows: Sequence[ResultRow]) -> dict[str, tuple[int, int]]:
    """Per evaluator: (passed, applicable) over the rows."""
    result = {}
    for name in EVALUATORS:
        marks = [row.marks()[name] for row in rows]
        applicable = [m for m in marks if m is not None]
        result[name] = (sum(applicable), len(applicable))
    return result


def write_results(path: Path, header: Mapping[str, str], rows: Sequence[ResultRow]) -> None:
    """Write `eval/results.md`: header lines, the results table and a totals line per evaluator."""
    lines = ["# Evaluation results", ""]
    lines += [f"- {name}: {value}" for name, value in header.items()]
    lines += ["", "| " + " | ".join(COLUMNS) + " |", "|" + "---|" * len(COLUMNS)]
    lines += [_row_line(row) for row in rows]
    lines += ["", "## Totals", ""]
    for name, (passed, applicable) in totals(rows).items():
        skipped = len(rows) - applicable
        suffix = f" ({skipped} not applicable)" if skipped else ""
        lines.append(f"- {name}: {passed}/{applicable}{suffix}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
