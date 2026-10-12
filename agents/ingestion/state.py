"""What the ingestion graph carries (spec 01 §7 "Ingestion graph", BR-111, D-073).

Three kinds of data, kept apart on purpose:
- `IngestionState`: the graph state. Every node's input and output is traced and the state is
  checkpointed at a pause, so it stays light: plain JSON-like values, per Table at most the first
  20 rows, never the PDF bytes or a DataFrame.
- `RunStore`: the per-run store, outside the state, keyed by `thread_id`. It holds the bytes, the
  open PyMuPDF document and the full `ExtractedTable`s, and is emptied when the run ends.
- `IngestionDeps`: everything a node needs from outside (settings, models, index, the store),
  injected when the graph is built so tests pass stubs.

The shapes the UI reads (the pause question, the run result) live here too, so the nodes, the
graph and the UI share one definition.
"""

import operator
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, TypedDict

import pymupdf

from agents.ingestion.schemas import ExtractedTable
from services.llm import make_chat_model, make_embeddings
from services.settings import Settings
from services.vector_store import IndexClient, open_index

# --- Graph state (light: BR-111) -------------------------------------------------------------------


class TableState(TypedDict):
    """One readable Table as the state sees it: facts, context and what the LLM is shown."""

    table_id: str
    pages: list[int]
    columns: list[str]
    dtypes: list[str]  # `dtype_name` of each column, in column order: int64 | float64 | text
    hints: dict[str, list[str]]  # per column name: `percent`, `currency: <symbol>`
    row_headers: list[str]  # complete (SPEC §7 lists them); only `rows` is capped
    rows: list[str]  # the first ROWS_TO_LLM rows as `a | b` lines (`rows_as_text`)
    n_rows: int
    context: dict[str, str] | None  # the five `TableContext` fields; None until `collect_context`


class SkippedPart(TypedDict):
    """Something the run could not index (FR-119, FR-132, FR-141). Never carries feedback (BR-106).

    - `no_text_pages`: a run of consecutive pages without selectable text (`table_id` is "").
    - `unreadable_table`: a table whose cells are mostly `�`; one page.
    - `table`: a Table skipped after its last attempt or by the size guard; `caption` from its context.
    """

    kind: Literal["no_text_pages", "unreadable_table", "table"]
    pages: list[int]
    table_id: str
    caption: str


class AssembledTable(TypedDict):
    """A valid Table, ready for `index`: the `TableMetadata` dump and its flat Index metadata."""

    metadata: dict[str, Any]  # `TableMetadata.model_dump(mode="json")`
    record_metadata: dict[str, Any]  # `index_metadata(...)`, already under the size guard


class Outcome(TypedDict):
    """How the run ended. Any node that writes `outcome` ends the run."""

    status: Literal["failed", "cancelled", "no_tables", "nothing_indexed", "indexed"]
    message: str  # the chat sentence (BR-106: no service name, no feedback)


class IngestionState(TypedDict, total=False):
    """The graph state (SPEC §7, BR-111).

    The run's input sets `thread_id`, `source_file`, `max_retries`, and `assembled` / `skipped` as
    `[]`; the nodes fill the rest. `assembled` and `skipped` are appended to (a node returns only
    its new items); every other key is replaced by the value a node returns.
    """

    thread_id: str
    source_file: str
    max_retries: int  # `INGESTION_MAX_RETRIES`; routers compare `attempts` with it
    document_sha: str  # full hex, set by `load_pdf`
    page_count: int
    tables: list[TableState]  # readable Tables in reading order, set by `extract_tables`
    image_pages: list[int]  # FR-121
    current: int  # 0-based index into `tables`
    attempts: int  # `enrich` calls for the current Table
    feedback: list[str]  # sentences from the last `validate`; [] = valid
    answer: dict[str, Any] | None  # the last answer as a dict (parsed or raw)
    assembled: Annotated[list[AssembledTable], operator.add]
    skipped: Annotated[list[SkippedPart], operator.add]
    outcome: Outcome


# --- Pauses and the run result (what the UI reads) -------------------------------------------------


class Choice(TypedDict):
    value: Literal["continue", "index", "cancel"]
    label: str


class PauseQuestion(TypedDict):
    """The value passed to LangGraph `interrupt` by `ask_unreadable` and `ask_skipped`.

    Kept in parts so the UI can escape PDF-derived text (captions) in the bullets.
    """

    pause: Literal["ask_unreadable", "ask_skipped"]
    intro: str
    bullets: list[str]
    question: str
    choices: list[Choice]


def question_text(question: PauseQuestion) -> str:
    """The whole question as plain text: intro, one `- ` line per bullet, then the question."""
    return "\n".join([question["intro"], *(f"- {bullet}" for bullet in question["bullets"]), question["question"]])


@dataclass(frozen=True)
class RunResult:
    """What one call to `run_ingestion` / `resume_ingestion` returns.

    `status` is `paused` while a question waits (then `question` is set and the per-run store is
    kept) and `finished` once the run ended (then `values["outcome"]` is set and the store is empty).
    """

    thread_id: str
    status: Literal["paused", "finished"]
    question: PauseQuestion | None
    values: dict[str, Any]  # the graph state after this call


# --- Per-run store (outside the state: BR-111, D-073) ------------------------------------------------


@dataclass
class RunData:
    """What one run keeps outside the state: the bytes, the open document, the full Tables."""

    pdf: bytes
    document: pymupdf.Document | None = None
    tables: dict[str, ExtractedTable] = field(default_factory=dict)  # by table_id, frames included


class RunStore:
    """In-memory `RunData` by `thread_id`. The PDF is never written to disk (FR-101)."""

    def __init__(self) -> None:
        self._runs: dict[str, RunData] = {}

    def open(self, thread_id: str, pdf: bytes) -> RunData:
        """Start keeping a run's data. A thread id already in use raises `ValueError`."""
        if thread_id in self._runs:
            raise ValueError(f"Run {thread_id!r} is already open.")
        data = RunData(pdf=pdf)
        self._runs[thread_id] = data
        return data

    def get(self, thread_id: str) -> RunData:
        """The data of an open run; `KeyError` when it is not open."""
        return self._runs[thread_id]

    def close(self, thread_id: str) -> None:
        """Close the run's document and forget the run. Closing an unknown run does nothing."""
        data = self._runs.pop(thread_id, None)
        if data is not None and data.document is not None:
            data.document.close()

    def thread_ids(self) -> list[str]:
        """The open runs, for tests (BR-111: empty once every run ended)."""
        return sorted(self._runs)


# --- Dependencies ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class IngestionDeps:
    """Everything the nodes use from outside the state.

    The chat model is a factory called with `settings` by `enrich`, so the model is always
    `LLM_MODEL` (FR-127); tests pass `ScriptedChatModel.build`. The Table store has no field: it is
    `services.table_store.TABLE_STORE_DIR`, which tests move with the `table_store_dir` fixture.
    """

    settings: Settings
    embeddings: Any
    index: Any
    make_chat_model: Callable[[Settings], Any] = make_chat_model
    runs: RunStore = field(default_factory=RunStore)


def make_deps(settings: Settings, client: IndexClient | None = None) -> IngestionDeps:
    """The production deps: proxy embeddings and the Octi index (`open_index` asks Pinecone once)."""
    return IngestionDeps(settings, embeddings=make_embeddings(settings), index=open_index(settings, client))
