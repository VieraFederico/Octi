"""The five deterministic checks on an `enrich` answer (spec 01 FR-131, D-063).

No LLM and no I/O: `validate` returns one plain sentence per failed check, written for the model to
read on the next attempt (FR-132). An empty list means the answer is valid. The schema decides
syntax (types, limits); these checks decide the semantics the schema cannot: do the column names
match, is anything empty, is the name a placeholder, does a percent column say so.
"""

import re
from collections import Counter
from collections.abc import Sequence
from typing import Any

from pydantic import ValidationError

from agents.ingestion.schemas import ExtractedTable, TableEnrichment

# Placeholder names: `Table`, `Table 2`, `Data`, `Untitled`, in any case (FR-131 check 4).
GENERIC_NAME = re.compile(r"(table(\s+\d+)?|data|untitled)", re.IGNORECASE)


def validate(answer: TableEnrichment | dict[str, Any], table: ExtractedTable) -> list[str]:
    """Feedback sentences for `answer`, empty when it passes all five checks.

    `answer` is a parsed `TableEnrichment`, or the raw dict the model produced when it did not parse
    into one (S01-D-015); a dict is checked against the model first (check 1).
    """
    if isinstance(answer, TableEnrichment):
        parsed = answer
    else:
        try:
            parsed = TableEnrichment.model_validate(answer)
        except ValidationError as exc:
            # Without a parsed answer the other checks have nothing to read; the model fixes the
            # shape first and the next attempt is checked in full.
            return [_shape_sentence(error) for error in exc.errors()]

    return [
        *_column_feedback(parsed, table.columns),
        *_empty_feedback(parsed),
        *_generic_name_feedback(parsed),
        *_percent_feedback(parsed, table),
    ]


# 1. Shape ---------------------------------------------------------------------------------------


def _shape_sentence(error: Any) -> str:
    """One sentence for one pydantic error, naming the field like `columns[2].unit`."""
    path = ""
    for part in error["loc"]:
        path += f"[{part}]" if isinstance(part, int) else f".{part}" if path else str(part)
    kind = error["type"]
    if kind == "missing":
        return f"The field {path} is missing."
    if kind == "string_too_long":
        return f"The field {path} is too long: at most {error['ctx']['max_length']} characters."
    return f"The field {path} is not valid: {error['msg']}."


# 2. Same columns --------------------------------------------------------------------------------


def _column_feedback(answer: TableEnrichment, expected: Sequence[str]) -> list[str]:
    given = [column.name for column in answer.columns]
    counts = Counter(given)
    feedback = [f'Column "{name}" is missing; describe it.' for name in expected if name not in counts]
    feedback += [
        f'"{name}" is not a column of this table; remove it or use the exact name from the Columns list.'
        for name in counts
        if name not in expected
    ]
    feedback += [f'"{name}" appears {count} times; describe each column once.' for name, count in counts.items() if count > 1]
    if not feedback and given != list(expected):
        feedback.append(f"The columns are not in the listed order; use this order: {', '.join(expected)}.")
    return feedback


# 3. Not empty -----------------------------------------------------------------------------------


def _empty_feedback(answer: TableEnrichment) -> list[str]:
    feedback = []
    if not answer.name.strip():
        feedback.append("The table name is empty; write a name.")
    if not answer.description.strip():
        feedback.append("The table description is empty; write 2 to 4 sentences.")
    feedback += [
        f'The description of column "{column.name}" is empty; write what the column holds.'
        for column in answer.columns
        if not column.description.strip()
    ]
    return feedback


# 4. Not generic ---------------------------------------------------------------------------------


def _generic_name_feedback(answer: TableEnrichment) -> list[str]:
    name = answer.name.strip()
    if name and GENERIC_NAME.fullmatch(name):
        return [f'The table name "{name}" is a placeholder; name what the table measures and how it is broken down.']
    return []


# 5. Percent agrees ------------------------------------------------------------------------------


def _percent_feedback(answer: TableEnrichment, table: ExtractedTable) -> list[str]:
    units: dict[str, str] = {}
    for column in answer.columns:
        units.setdefault(column.name, column.unit)  # the first entry of a repeated name; check 2 reports repeats
    feedback = []
    for name in table.columns:
        if "percent" not in table.hints.get(name, []) or name not in units:
            continue  # a column the answer left out is check 2's business
        unit = units[name].lower()
        if "%" not in unit and "percent" not in unit:
            feedback.append(
                f'Column "{name}" holds percentages, so its unit must contain "%" or "percent" (you wrote "{units[name]}").'
            )
    return feedback
