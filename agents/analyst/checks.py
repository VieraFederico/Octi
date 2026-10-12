"""Plain-code decisions of the Analyst: no LLM, no I/O, fully unit-tested.

- `check_selection`: is `select`'s answer usable? (FR-212, BR-209)
- `classify_attempt`: did a sandbox run fail, and what feedback does the next attempt get? (FR-221)
- `merge_status`: per-part outcomes and the Answer status (FR-224, FR-225, BR-202)
- `check_numbers`: is every number in the answer text backed by the facts? (FR-229)
- `template_answer`: the answer built by code when `respond` cannot be trusted (FR-229)

Unit coverage of this module is staged verification (D-118).
"""

import json
import re
from collections import Counter
from collections.abc import Collection, Sequence
from decimal import ROUND_HALF_UP, Decimal

from pydantic import TypeAdapter, ValidationError

from agents.analyst.schemas import (
    AnswerFacts,
    AnswerStatus,
    AttemptCheck,
    EmittedPart,
    PartOutcome,
    PartSelection,
    QueryPlan,
    TableSelection,
    TableSource,
    Value,
)

# Sentences fixed by the spec (verbatim).
SELECTION_FAILED_REASON = "I couldn't decide which tables to use."  # FR-212
FAILED_PART_REASON = "I couldn't compute this part."  # FR-222
TIMEOUT_FEEDBACK = "The code ran longer than {seconds} s. Avoid loops over rows; use pandas operations."  # FR-221
EMIT_FEEDBACK = "The code must end by calling `emit(parts)` exactly once."  # FR-221
NUMBER_FEEDBACK = "The number {number} is not in the results."  # FR-229
STDERR_TAIL_CHARS = 2_000  # FR-221, SPEC §7 code constant

# Feedback sentences the spec leaves open (S02-D-004).
UNKNOWN_TABLE_FEEDBACK = (
    'Part {part} uses the table id "{table_id}", which is not a candidate table. '
    'Use only the ids listed under "Candidate tables".'
)
MISSING_PART_FEEDBACK = "Part {part} has no entry. Give exactly one entry for every question part."
DUPLICATE_PART_FEEDBACK = "Part {part} has more than one entry. Give exactly one entry for every question part."
EXTRA_PART_FEEDBACK = "Part {part} is not a question part. Give entries only for the question parts."
NO_TABLE_FEEDBACK = 'Part {part} is "answerable" but names no table. List the ids of the tables it needs.'
EMPTY_MISSING_FEEDBACK = (
    'Part {part} has the verdict "{verdict}" but "missing" is empty. '
    "Say what is missing and what the related table does contain."
)
SILENT_EXIT_FEEDBACK = "The code stopped with exit code {exit_code} and printed no error message."
NOT_JSON_DETAIL = 'The last line of the output is not a JSON object with a "parts" list.'
WRONG_PARTS_FEEDBACK = "Call `emit` with exactly one entry for each of these parts: {expected}."
WRONG_PARTS_MISSING = "Missing parts: {parts}."
WRONG_PARTS_EXTRA = "Extra parts: {parts}."
WRONG_PARTS_REPEATED = "Repeated parts: {parts}."
EMPTY_MISSING_REASON = "The calculation found no value for this part."

_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")
_ENGLISH_GROUPED = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?")
_ENGLISH_PLAIN = re.compile(r"\d+(?:\.\d+)?")
_SPANISH_GROUPED = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?")
_SPANISH_PLAIN = re.compile(r"\d+(?:,\d+)?")
_SCALE_RE = re.compile(
    r"\s*(?:thousands?|millions?|billions?|millones|millón|miles|bn|mil|k|M)\b",
    re.IGNORECASE,
)
_PERCENT_RE = re.compile(r"\s*(?:%|percent\b|por\s+ciento\b)", re.IGNORECASE)
_SCALE_FACTORS = tuple(Decimal(1000) ** exponent for exponent in range(-3, 4))
_EMITTED_PARTS = TypeAdapter(list[EmittedPart])


def check_selection(selection: TableSelection, plan: QueryPlan, candidate_ids: Collection[str]) -> list[str]:
    """Feedback sentences for a `TableSelection`, one per problem; empty means valid (FR-212).

    Problems: a `table_id` that is not a Candidate table (one sentence per id and part); a Question
    part with no entry, with more than one entry, or an entry for a part the plan does not have; an
    `answerable` entry with no `table_ids` (S02-D-004); an empty `missing` when the verdict is not
    `answerable`.
    """
    feedback: list[str] = []
    candidates = set(candidate_ids)
    plan_numbers = sorted({part.number for part in plan.parts})
    plan_number_set = set(plan_numbers)
    seen_unknown: set[tuple[int, str]] = set()
    counts: dict[int, int] = {}
    for entry in selection.parts:
        counts[entry.part] = counts.get(entry.part, 0) + 1
        for table_id in entry.table_ids:
            if table_id in candidates or (entry.part, table_id) in seen_unknown:
                continue
            seen_unknown.add((entry.part, table_id))
            feedback.append(UNKNOWN_TABLE_FEEDBACK.format(part=entry.part, table_id=table_id))
        if entry.part not in plan_number_set:
            feedback.append(EXTRA_PART_FEEDBACK.format(part=entry.part))
        if entry.verdict == "answerable" and not entry.table_ids:
            feedback.append(NO_TABLE_FEEDBACK.format(part=entry.part))
        if entry.verdict != "answerable" and entry.missing.strip() == "":
            feedback.append(EMPTY_MISSING_FEEDBACK.format(part=entry.part, verdict=entry.verdict))
    for number in plan_numbers:
        count = counts.get(number, 0)
        if count == 0:
            feedback.append(MISSING_PART_FEEDBACK.format(part=number))
        elif count > 1:
            feedback.append(DUPLICATE_PART_FEEDBACK.format(part=number))
    return feedback


def classify_attempt(
    exit_code: int,
    timed_out: bool,
    stdout: str,
    stderr: str,
    answerable_parts: Collection[int],
    timeout_seconds: int,
) -> AttemptCheck:
    """Classify one sandbox run (FR-221), checked in this order:

    1. `timed_out` → `timeout` with `TIMEOUT_FEEDBACK` naming `timeout_seconds`;
    2. `exit_code != 0` → `python_error` with the last `STDERR_TAIL_CHARS` of stderr
       (`SILENT_EXIT_FEEDBACK` when stderr is blank);
    3. the last non-blank stdout line is not `{"parts": [...]}` of valid `EmittedPart`s →
       `invalid_output` with `EMIT_FEEDBACK` plus the schema detail;
    4. the emitted part numbers differ from `answerable_parts` → `wrong_parts`.
    Otherwise `failure None` with the parsed parts; a part emitted `missing` is not a failure.
    """
    if timed_out:
        return AttemptCheck(failure="timeout", feedback=TIMEOUT_FEEDBACK.format(seconds=timeout_seconds))
    if exit_code != 0:
        if stderr.strip() == "":
            feedback = SILENT_EXIT_FEEDBACK.format(exit_code=exit_code)
        else:
            feedback = stderr[-STDERR_TAIL_CHARS:]
        return AttemptCheck(failure="python_error", feedback=feedback)
    parsed, detail = _parse_emit_line(_last_non_blank_line(stdout))
    if detail is not None or parsed is None:
        return AttemptCheck(failure="invalid_output", feedback=f"{EMIT_FEEDBACK} {detail}")
    mismatch = _wrong_parts_feedback(parsed, answerable_parts)
    if mismatch is not None:
        return AttemptCheck(failure="wrong_parts", feedback=mismatch)
    return AttemptCheck(failure=None, feedback="", emitted=parsed)


def merge_status(
    selection: TableSelection,
    emitted: Sequence[EmittedPart],
    failed: bool,
) -> tuple[list[PartOutcome], AnswerStatus]:
    """Per-part outcomes, ordered by part number, and the Answer status (D-089, FR-224, FR-225).

    `emitted` comes from the valid attempt (empty when none); `failed` is True when the attempts were
    used up. Values are kept only for `answered` outcomes.
    """
    emitted_by_part: dict[int, EmittedPart] = {}
    for item in emitted:
        emitted_by_part.setdefault(item.part, item)
    outcomes = [
        _outcome_for(entry, emitted_by_part.get(entry.part), failed) for entry in selection.parts
    ]
    outcomes.sort(key=lambda outcome: outcome.part)
    return outcomes, _answer_status(outcomes)


def check_numbers(text: str, facts: AnswerFacts) -> list[str]:
    """One `NUMBER_FEEDBACK` sentence per number in `text` that the facts do not back (FR-229).

    Numbers appear as written, in order, without repeats; an empty list means the text passes. The
    sentences are the feedback of the `respond` retry.
    """
    fact_numbers = _fact_numbers(facts)
    computed = _computed_values(facts)
    reported: list[str] = []
    seen: set[str] = set()
    for match in _NUMBER_RE.finditer(text):
        token = match.group()
        if token in seen:
            continue
        if _number_is_backed(token, text[match.end() :], fact_numbers, computed):
            continue
        seen.add(token)
        reported.append(NUMBER_FEEDBACK.format(number=token))
    return reported


def template_answer(facts: AnswerFacts) -> str:
    """An English answer built only from `facts`: results, method, sources, unanswered parts (FR-229).

    It never shows a value for `cannot_answer` (FR-228), and its own numbers pass `check_numbers`.
    """
    outcomes = sorted(facts.outcomes, key=lambda outcome: outcome.part)
    show_values = facts.answer_status != "cannot_answer"
    lines: list[str] = []
    answered_any = False
    for outcome in outcomes:
        if outcome.outcome == "answered" and show_values:
            lines.append(_answered_line(outcome))
            answered_any = True
    approach = facts.approach.strip()
    if answered_any and approach:
        lines.append(f"Method: {_with_period(approach)}")
    if facts.tables:
        sources = "; ".join(_source_item(table) for table in facts.tables)
        lines.append(f"Sources: {sources}.")
    for outcome in outcomes:
        if outcome.outcome != "answered":
            lines.append(_unanswered_line(outcome))
    return " ".join(lines)


def _last_non_blank_line(stdout: str) -> str | None:
    for line in reversed(stdout.splitlines()):
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def _parse_emit_line(line: str | None) -> tuple[list[EmittedPart] | None, str | None]:
    if line is None:
        return None, NOT_JSON_DETAIL
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return None, NOT_JSON_DETAIL
    if not isinstance(payload, dict) or not isinstance(payload.get("parts"), list):
        return None, NOT_JSON_DETAIL
    try:
        return _EMITTED_PARTS.validate_python(payload["parts"]), None
    except ValidationError as exc:
        detail = "; ".join(
            f"{'.'.join(str(piece) for piece in error['loc'])}: {error['msg']}" for error in exc.errors()
        )
        return None, detail


def _wrong_parts_feedback(emitted: list[EmittedPart], answerable_parts: Collection[int]) -> str | None:
    expected = sorted(set(answerable_parts))
    expected_set = set(expected)
    counts = Counter(part.part for part in emitted)
    missing = [part for part in expected if counts[part] == 0]
    extra = sorted(part for part in counts if part not in expected_set)
    repeated = sorted(part for part in counts if counts[part] > 1)
    if not missing and not extra and not repeated:
        return None
    sentences = [WRONG_PARTS_FEEDBACK.format(expected=", ".join(str(part) for part in expected))]
    if missing:
        sentences.append(WRONG_PARTS_MISSING.format(parts=", ".join(str(part) for part in missing)))
    if extra:
        sentences.append(WRONG_PARTS_EXTRA.format(parts=", ".join(str(part) for part in extra)))
    if repeated:
        sentences.append(WRONG_PARTS_REPEATED.format(parts=", ".join(str(part) for part in repeated)))
    return " ".join(sentences)


def _outcome_for(entry: PartSelection, emitted: EmittedPart | None, failed: bool) -> PartOutcome:
    if entry.verdict != "answerable":
        return PartOutcome(part=entry.part, outcome="missing", values={}, reason=entry.missing)
    if failed or emitted is None:
        return PartOutcome(part=entry.part, outcome="failed", values={}, reason=FAILED_PART_REASON)
    if emitted.status == "missing":
        reason = emitted.missing if emitted.missing.strip() else EMPTY_MISSING_REASON
        return PartOutcome(part=entry.part, outcome="missing", values={}, reason=reason)
    return PartOutcome(part=entry.part, outcome="answered", values=dict(emitted.values), reason="")


def _answer_status(outcomes: list[PartOutcome]) -> AnswerStatus:
    answered = sum(outcome.outcome == "answered" for outcome in outcomes)
    if answered == 0:
        return "cannot_answer"
    if answered == len(outcomes):
        return "answered"
    return "partial"


def _readings(token: str) -> list[tuple[Decimal, int]]:
    readings: list[tuple[Decimal, int]] = []
    if _ENGLISH_GROUPED.fullmatch(token):
        fraction = token.partition(".")[2]
        readings.append((Decimal(token.replace(",", "")), len(fraction)))
    elif _ENGLISH_PLAIN.fullmatch(token):
        fraction = token.partition(".")[2]
        readings.append((Decimal(token), len(fraction)))
    if _SPANISH_GROUPED.fullmatch(token):
        fraction = token.partition(",")[2]
        normalized = token.replace(".", "").replace(",", ".")
        readings.append((Decimal(normalized), len(fraction)))
    elif _SPANISH_PLAIN.fullmatch(token):
        fraction = token.partition(",")[2]
        readings.append((Decimal(token.replace(",", ".")), len(fraction)))
    return readings


def _within(reading: Decimal, decimals: int, target: Decimal) -> bool:
    tolerance = Decimal("0.5") * (Decimal(10) ** -decimals)
    return abs(reading - target) <= tolerance


def _fact_numbers(facts: AnswerFacts) -> list[Decimal]:
    numbers: list[Decimal] = []
    texts = [facts.question, facts.approach]
    for part in facts.parts:
        numbers.append(Decimal(part.number))
        texts.extend([part.text, *part.entities, *part.metrics, *part.periods, *part.operations])
    for outcome in facts.outcomes:
        numbers.append(Decimal(outcome.part))
        texts.append(outcome.reason)
        for label, value in outcome.values.items():
            texts.append(label)
            if isinstance(value, str):
                texts.append(value)
    for table in facts.tables:
        texts.extend([table.name, table.source_file])
        numbers.extend(Decimal(page) for page in table.pages)
    for text in texts:
        for match in _NUMBER_RE.finditer(text):
            numbers.extend(reading for reading, _decimals in _readings(match.group()))
    return numbers


def _computed_values(facts: AnswerFacts) -> list[Decimal]:
    values: list[Decimal] = []
    for outcome in facts.outcomes:
        if outcome.outcome != "answered":
            continue
        for value in outcome.values.values():
            if isinstance(value, bool) or not isinstance(value, int | float):
                continue
            values.append(abs(Decimal(str(value))))
    return values


def _number_is_backed(
    token: str,
    rest: str,
    fact_numbers: list[Decimal],
    computed: list[Decimal],
) -> bool:
    readings = _readings(token)
    if not readings:
        return False
    has_scale = _SCALE_RE.match(rest) is not None
    has_percent = _PERCENT_RE.match(rest) is not None
    for reading, decimals in readings:
        if any(reading == number for number in fact_numbers):
            return True
        for magnitude in computed:
            targets = [magnitude]
            if has_scale:
                targets.extend(magnitude * factor for factor in _SCALE_FACTORS)
            if has_percent:
                targets.append(magnitude * 100)
            if any(_within(reading, decimals, target) for target in targets):
                return True
    return False


def _format_value(value: Value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return f"{value:,}"
    decimal = Decimal(str(value))
    negative = decimal < 0
    rounded = abs(decimal).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    body = f"{rounded:,.4f}".rstrip("0").rstrip(".")
    if body in {"", "-"}:
        body = "0"
    return f"-{body}" if negative else body


def _with_period(text: str) -> str:
    return text if text.endswith(".") else f"{text}."


def _answered_line(outcome: PartOutcome) -> str:
    pairs = "; ".join(f"{label} = {_format_value(value)}" for label, value in outcome.values.items())
    if not pairs:
        return f"Question {outcome.part}."
    return f"Question {outcome.part}: {pairs}."


def _unanswered_line(outcome: PartOutcome) -> str:
    reason = outcome.reason.strip()
    if not reason:
        return f"Question {outcome.part} could not be answered."
    return f"Question {outcome.part} could not be answered: {_with_period(reason)}"


def _source_item(table: TableSource) -> str:
    if len(table.pages) == 1:
        return f"{table.name} ({table.source_file}, page {table.pages[0]})"
    if len(table.pages) > 1:
        pages = ", ".join(str(page) for page in table.pages)
        return f"{table.name} ({table.source_file}, pages {pages})"
    return f"{table.name} ({table.source_file})"
