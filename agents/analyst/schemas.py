"""Data shapes of the Analyst agent.

Two kinds live here:
- the SPEC §7 Pydantic models: the four LLM outputs (`QueryPlan`, `TableSelection`, `CodeDraft`,
  `FinalAnswer`), one entry of the sandbox's `emit` line (`EmittedPart`) and the per-part result of
  the status merge (`PartOutcome`);
- plain dataclasses that code passes between the prompts, the checks and (later) the graph: a turn of
  the conversation window, the previous code attempt, the result of classifying an attempt, and the
  facts the answer is written from (S02-D-002).

Counts and conditional rules (at least one part, 1–3 search phrases, `missing` required unless the
verdict is `answerable`) are told to the LLM in the field descriptions and enforced by code, not by
Pydantic validators, so a slightly wrong answer gets feedback or is trimmed instead of failing to
parse (FR-212, S02-D-001).
"""

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

Verdict = Literal["answerable", "missing_data", "ambiguous"]
EmitStatus = Literal["answered", "missing"]
Outcome = Literal["answered", "missing", "failed"]
AnswerStatus = Literal["answered", "partial", "cannot_answer"]
FailureKind = Literal["python_error", "timeout", "invalid_output", "wrong_parts"]
Value = float | int | str

# --- The LLM's structured outputs (SPEC §7) ------------------------------------------------------
# The `Field(description=...)` texts are the field rules the LLM sees, so they are written for it.


class QuestionPart(BaseModel):
    """One sub-question of the user's question."""

    number: int = Field(description="Position of the part in the question, starting at 1.")
    text: str = Field(description="The sub-question on its own, as a complete question.")
    entities: list[str] = Field(description="Companies, regions, products or groups the part is about.")
    metrics: list[str] = Field(description="The measures the part asks for, e.g. 'net revenue', 'unemployment rate'.")
    periods: list[str] = Field(description="The years, quarters or months the part asks about, as written.")
    operations: list[str] = Field(
        description="The calculations the part needs, e.g. 'sum', 'growth rate', 'ratio', 'compare'; empty to read a value."
    )


class QueryPlan(BaseModel):
    """`understand`'s structured output: the question rewritten to stand alone, its parts and search phrases."""

    standalone_question: str = Field(
        description=(
            "The latest user message rewritten as a question that needs no earlier turn, in the "
            "language of that message. A question that already stands alone is copied as written."
        )
    )
    parts: list[QuestionPart] = Field(
        description="The sub-questions, at least one, numbered from 1. A question asking for one thing has one part."
    )
    search_phrases: list[str] = Field(
        description=(
            "1 to 3 short English phrases, one per kind of data needed, worded like a table "
            "description, e.g. 'annual revenue by year'."
        ),
    )


class PartSelection(BaseModel):
    """The verdict for one Question part."""

    part: int = Field(description="The number of the question part this entry is about.")
    table_ids: list[str] = Field(
        description="Ids of the candidate tables this part needs (or the closest related ones), copied exactly."
    )
    verdict: Verdict = Field(
        description=(
            "'answerable' when the tables hold every value the part needs; 'missing_data' when a "
            "period, entity, comparison value or outside data is absent; 'ambiguous' when the "
            "choice of column or unit changes the result."
        )
    )
    missing: str = Field(
        description=(
            "Empty when the verdict is 'answerable'. Otherwise what is missing (or the options for "
            "an ambiguous part) and what the related table does contain."
        )
    )


class TableSelection(BaseModel):
    """`select`'s structured output: one entry per Question part."""

    parts: list[PartSelection] = Field(description="Exactly one entry for every question part, in part order.")


class CodeDraft(BaseModel):
    """`generate_code`'s structured output."""

    code: str = Field(
        description=(
            "Python code that uses only `tables[...]`, pandas, numpy and the standard library, and "
            "ends by calling `emit(parts)` exactly once."
        )
    )
    approach: str = Field(
        description="1 to 2 sentences on how the result is calculated, stating every conversion done."
    )


class EmittedPart(BaseModel):
    """One entry of the `{"parts": [...]}` JSON line that `emit` prints last."""

    part: int = Field(description="The number of the question part.")
    status: EmitStatus = Field(description="'answered' with values, or 'missing' with a reason.")
    values: dict[str, Value] = Field(
        default_factory=dict, description="Label → computed value, for an answered part."
    )
    missing: str = Field(default="", description="Why the part could not be computed, for a missing part.")


class PartOutcome(BaseModel):
    """`merge_status`'s result for one Question part (D-089)."""

    part: int = Field(description="The number of the question part.")
    outcome: Outcome = Field(description="'answered', 'missing' or 'failed' (attempts used up).")
    values: dict[str, Value] = Field(
        default_factory=dict, description="The computed values; empty unless the outcome is 'answered'."
    )
    reason: str = Field(default="", description="Why the part is missing or failed; empty when answered.")


class FinalAnswer(BaseModel):
    """`respond`'s structured output."""

    text: str = Field(
        description=(
            "The answer in 2 to 6 sentences, in the language of the question: results first, then "
            "the method with every conversion, then the sources, then each unanswered part with its reason."
        )
    )


# --- Plain data passed between the pieces (S02-D-002) --------------------------------------------


@dataclass(frozen=True)
class Turn:
    """One earlier turn of the conversation window: a question and its Analysis answer text (FR-203)."""

    question: str
    answer: str


@dataclass(frozen=True)
class PreviousAttempt:
    """What a code retry prompt carries: the previous attempt's code and its feedback (FR-216)."""

    code: str
    feedback: str


@dataclass(frozen=True)
class AttemptCheck:
    """The classification of one sandbox run (FR-221).

    A failed attempt has a `failure` kind and its `feedback`, and no `emitted` parts. A valid attempt
    has `failure None`, `feedback ""` and the parsed parts, which may include `missing` ones.
    """

    failure: FailureKind | None
    feedback: str = ""
    emitted: list[EmittedPart] = field(default_factory=list)


@dataclass(frozen=True)
class TableSource:
    """A Selected table as the answer cites it: its name, Document and pages."""

    name: str
    source_file: str
    pages: list[int]


@dataclass(frozen=True)
class AnswerFacts:
    """Everything `respond`, the number check and the template answer may use (FR-227).

    `outcomes` carry values only for `answered` parts, so a `cannot_answer` run holds no value
    (FR-228). `answer_status` is read-only for the answer writer (BR-202).
    """

    question: str
    parts: list[QuestionPart]
    outcomes: list[PartOutcome]
    approach: str
    tables: list[TableSource]
    answer_status: AnswerStatus
