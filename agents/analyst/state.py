"""Checkpointable Analyst state and injected dependencies (spec 02 §7, D-120).

Values passed between nodes stay in state. The catalog is only an input to the library check;
later nodes use Candidate tables. Settings, clients and table files never enter state.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TypedDict

from agents.analyst.schemas import (
    AnswerStatus, CodeDraft, FailureKind, PartOutcome, QueryPlan, TableSelection, Turn,
)
from agents.ingestion.indexing import load_catalog
from agents.ingestion.schemas import CatalogEntry
from services import table_store
from services.llm import make_chat_model, make_embeddings
from services.sandbox import SandboxResult, run_script
from services.settings import Settings
from services.vector_store import open_index


class AnalysisError(TypedDict):
    kind: Literal["llm", "vector_store", "sandbox"]
    message: str


class SandboxOutput(TypedDict):
    exit_code: int
    timed_out: bool
    stdout: str
    stderr: str


class Attempt(TypedDict):
    code: str
    approach: str
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    failure: FailureKind | None
    feedback: str


class AnalystState(TypedDict, total=False):
    """Spec §7's fields only: no catalog, DataFrame, settings, client or per-run scratch store."""

    question: str
    window: list[Turn]
    plan: QueryPlan | None
    candidates: list[CatalogEntry]
    selection: TableSelection | None
    selection_attempts: int
    selection_feedback: list[str]
    code_attempts: int
    code_draft: CodeDraft | None
    sandbox_result: SandboxOutput | None
    last_failure: FailureKind | None
    attempts_history: list[Attempt]
    part_outcomes: list[PartOutcome]
    answer_status: AnswerStatus | None
    answer: str | None
    error: AnalysisError | None


def table_file(table_id: str) -> Path:
    """Use spec 01's actual Parquet storage layout; the sandbox validates each id before copying."""
    return table_store.TABLE_STORE_DIR / f"{table_id}.parquet"


@dataclass(frozen=True)
class AnalystDeps:
    """Service seams for offline tests. None catalog means not loaded; [] means loaded and empty.

    Client construction is lazy inside the nodes, so a failure follows the graph's `fail` route.
    `sandbox_runner` owns its prepared folder's cleanup, like `services.sandbox.run_script`.
    An injected tracing client must use the Analyst masking hooks, as the production factory does.
    """

    settings: Settings
    catalog: list[CatalogEntry] | None = None
    embeddings: Any = None
    index: Any = None
    make_chat_model: Callable[[Settings], Any] = make_chat_model
    make_embeddings: Callable[[Settings], Any] = make_embeddings
    open_index: Callable[[Settings], Any] = open_index
    load_catalog: Callable[..., list[CatalogEntry]] = load_catalog
    table_file: Callable[[str], Path] = table_file
    sandbox_runner: Callable[[Path, int], SandboxResult] = run_script
    sandbox_base_dir: Path | None = None
    tracing_client: Any = None


def make_deps(settings: Settings, *, catalog: list[CatalogEntry] | None = None) -> AnalystDeps:
    """Production dependencies; building this object performs no model, index or sandbox call."""
    return AnalystDeps(settings=settings, catalog=catalog)
