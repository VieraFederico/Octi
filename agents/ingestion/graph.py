"""The LangGraph layer of the Ingestion agent (spec 01 §7 "Ingestion graph", FR-143, FR-153, FR-154).

- Routers: pure functions of the state that pick the next node (they read `outcome`, `current`,
  `attempts`, `feedback`, `max_retries`, `tables`, `skipped`, `assembled`).
- `build_graph(deps)`: the `StateGraph` with the nodes of `nodes.py` (deps bound), its conditional
  edges and an in-memory checkpointer (pauses, D-053).
- `run_ingestion` / `resume_ingestion`: one call each, streaming `stream_mode="updates"`, inside the
  tracing scope, with the run config of FR-153; they return a `RunResult`.
Contract: "Contract (Iteration 5)" in `specs/01-ingestion-plan-artifacts/CONTEXT.md`.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, Literal
from uuid import uuid4

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from langsmith.run_helpers import tracing_context

from agents.ingestion import nodes
from agents.ingestion.pdf.document import open_document
from agents.ingestion.pdf.tables import document_sha
from agents.ingestion.state import IngestionDeps, IngestionState, RunResult
from services.errors import DocumentError
from services.settings import Settings
from services.tracing import make_langsmith_client

Choice = Literal["continue", "index", "cancel"]
OnUpdate = Callable[[str, dict[str, Any]], None]  # (node name, that node's partial update)

NODE_NAMES = (
    "load_pdf",
    "extract_tables",
    "ask_unreadable",
    "collect_context",
    "enrich",
    "validate",
    "next_table",
    "ask_skipped",
    "index",
)


# --- Routers (pure) ----------------------------------------------------------------------------------


def route_after_load(state: IngestionState) -> str:
    """`END` when `outcome` is set (FR-105 … FR-107), else `extract_tables`."""
    if state.get("outcome"):
        return END
    return "extract_tables"


def route_after_extract(state: IngestionState) -> str:
    """`ask_unreadable` when a `no_text_pages` or `unreadable_table` part exists, else `collect_context`."""
    unreadable = {"no_text_pages", "unreadable_table"}
    if any(part["kind"] in unreadable for part in state.get("skipped", ())):
        return "ask_unreadable"
    return "collect_context"


def route_after_ask_unreadable(state: IngestionState) -> str:
    """`END` when cancelled (`outcome` set), else `collect_context`."""
    if state.get("outcome"):
        return END
    return "collect_context"


def route_after_context(state: IngestionState) -> str:
    """`index` when there are no Tables (FR-142), else `enrich`."""
    if not state.get("tables"):
        return "index"
    return "enrich"


def route_after_enrich(state: IngestionState) -> str:
    """`END` when `outcome` is set (FR-160), else `validate`."""
    if state.get("outcome"):
        return END
    return "validate"


def route_after_validate(state: IngestionState) -> str:
    """`enrich` when `feedback` is non-empty and `attempts <= max_retries` (FR-132), else `next_table`."""
    feedback = state.get("feedback") or []
    if feedback and state.get("attempts", 0) <= state.get("max_retries", 0):
        return "enrich"
    return "next_table"


def route_after_next_table(state: IngestionState) -> str:
    """`enrich` while `current < len(tables)`; then `ask_skipped` when a `table` part exists, else `index`."""
    tables = state.get("tables") or []
    if state.get("current", 0) < len(tables):
        return "enrich"
    if any(part["kind"] == "table" for part in state.get("skipped", ())):
        return "ask_skipped"
    return "index"


def route_after_ask_skipped(state: IngestionState) -> str:
    """`END` when cancelled (`outcome` set), else `index`."""
    if state.get("outcome"):
        return END
    return "index"


# --- Run settings --------------------------------------------------------------------------------------


def recursion_limit(table_count: int, max_retries: int) -> int:
    """FR-143: `10 + T × (2 × (R + 1) + 1)`."""
    return 10 + table_count * (2 * (max_retries + 1) + 1)


def table_upper_bound(pdf: bytes) -> tuple[int, int]:
    """`(tables PyMuPDF finds on all pages, page count)`, read before the graph runs (S01-D-023).

    The first number is at least the number of Tables the graph will enrich (dropping and joining
    only lower it), so `recursion_limit` can be computed before the call. A file `open_document`
    refuses gives `(0, 0)`: `load_pdf` then ends the run with its sentence.
    """
    try:
        document = open_document(pdf)
    except DocumentError:
        return (0, 0)
    try:
        found = sum(len(page.find_tables().tables) for page in document)
        return (found, document.page_count)
    finally:
        document.close()


def run_config(
    settings: Settings,
    *,
    source_file: str,
    document_sha: str,
    pages: int,
    thread_id: str,
    limit: int,
    run_id: str | None = None,
) -> RunnableConfig:
    """The config of one graph call (FR-153): `run_name` `Ingestion: <file>`, `tags` `["ingestion"]`,
    `metadata` with exactly `source_file`, `document_sha`, `pages`, `llm_model` (= `LLM_MODEL`),
    `max_retries` (= `INGESTION_MAX_RETRIES`), `thread_id`; `run_id` (a new `uuid4` when None),
    `configurable.thread_id` and `recursion_limit = limit`. No secret value (BR-107)."""
    return {
        "run_name": f"Ingestion: {source_file}",
        "tags": ["ingestion"],
        "metadata": {
            "source_file": source_file,
            "document_sha": document_sha,
            "pages": pages,
            "llm_model": settings.LLM_MODEL,
            "max_retries": settings.INGESTION_MAX_RETRIES,
            "thread_id": thread_id,
        },
        "run_id": uuid4() if run_id is None else run_id,
        "configurable": {"thread_id": thread_id},
        "recursion_limit": limit,
    }


@contextmanager
def tracing_scope(settings: Settings, client: Any = None) -> Iterator[None]:
    """FR-154: with tracing on, `langsmith.tracing_context(enabled=True, project_name=LANGSMITH_PROJECT,
    client=...)` so runs are traced even when no `LANGSMITH_*` variable is in the environment; the
    client is `client` or, when None, `make_langsmith_client(settings)` (it contacts LangSmith, which
    tracing does anyway; offline tests always pass `client`). With tracing off,
    `tracing_context(enabled=False)` and no client is built."""
    if not settings.LANGSMITH_TRACING:
        with tracing_context(enabled=False):
            yield
        return
    tracing_client = client if client is not None else make_langsmith_client(settings)
    with tracing_context(enabled=True, project_name=settings.LANGSMITH_PROJECT, client=tracing_client):
        yield


# --- The graph and its entry points ----------------------------------------------------------------------


def _bind(fn: Callable[..., Any], deps: IngestionDeps) -> Callable[[IngestionState], Any]:
    """Call `nodes.<name>(state, deps)` with `deps` fixed when the graph was built."""

    def bound(state: IngestionState) -> Any:
        return fn(state, deps)

    return bound


def build_graph(deps: IngestionDeps) -> CompiledStateGraph:
    """The ingestion `StateGraph(IngestionState)`: the nodes of `NODE_NAMES` (each `nodes.<name>` with
    `deps` bound), entry `load_pdf`, the routers above as conditional edges, `index → END`,
    compiled with an `InMemorySaver` checkpointer."""
    builder = StateGraph(IngestionState)
    for name in NODE_NAMES:
        builder.add_node(name, _bind(getattr(nodes, name), deps))
    builder.add_edge(START, "load_pdf")
    builder.add_conditional_edges("load_pdf", route_after_load)
    builder.add_conditional_edges("extract_tables", route_after_extract)
    builder.add_conditional_edges("ask_unreadable", route_after_ask_unreadable)
    builder.add_conditional_edges("collect_context", route_after_context)
    builder.add_conditional_edges("enrich", route_after_enrich)
    builder.add_conditional_edges("validate", route_after_validate)
    builder.add_conditional_edges("next_table", route_after_next_table)
    builder.add_conditional_edges("ask_skipped", route_after_ask_skipped)
    builder.add_edge("index", END)
    return builder.compile(checkpointer=InMemorySaver())


def _stream(
    graph: CompiledStateGraph,
    payload: Any,
    config: RunnableConfig,
    on_update: OnUpdate | None,
    thread_id: str,
) -> RunResult:
    """Stream one call and turn the checkpoint into a paused or finished `RunResult`."""
    for chunk in graph.stream(payload, config, stream_mode="updates"):
        if on_update is None:
            continue
        for name, update in chunk.items():
            if name == "__interrupt__":
                continue
            on_update(name, {} if update is None else update)
    snapshot = graph.get_state(config)
    values = dict(snapshot.values)
    if snapshot.interrupts:
        return RunResult(
            thread_id=thread_id,
            status="paused",
            question=snapshot.interrupts[0].value,
            values=values,
        )
    return RunResult(thread_id=thread_id, status="finished", question=None, values=values)


def _close_when_finished(deps: IngestionDeps, thread_id: str, result: RunResult) -> RunResult:
    if result.status == "finished":
        deps.runs.close(thread_id)
    return result


def run_ingestion(
    graph: CompiledStateGraph,
    deps: IngestionDeps,
    source_file: str,
    pdf: bytes,
    *,
    thread_id: str | None = None,
    on_update: OnUpdate | None = None,
) -> RunResult:
    """Start one Ingestion run (one `thread_id`, a new `uuid4` hex when None).

    Opens the run in `deps.runs` with the bytes; `document_sha(pdf)` and `table_upper_bound(pdf)` give
    the run config's `document_sha`, `pages` and `limit = recursion_limit(bound, R)`. Then streams
    the graph from the input state
    `{thread_id, source_file, max_retries: INGESTION_MAX_RETRIES, assembled: [], skipped: []}`
    with `stream_mode="updates"` inside `tracing_scope(deps.settings)` and `run_config(...)`,
    calling `on_update(node, update)` for each node update. Returns `paused` with the
    `PauseQuestion` when the graph waits at an `interrupt`; otherwise `finished`, after closing the
    run in `deps.runs`. The run is also closed when an exception escapes (then re-raised).
    """
    thread = uuid4().hex if thread_id is None else thread_id
    deps.runs.open(thread, pdf)
    try:
        sha = document_sha(pdf)
        bound, pages = table_upper_bound(pdf)
        config = run_config(
            deps.settings,
            source_file=source_file,
            document_sha=sha,
            pages=pages,
            thread_id=thread,
            limit=recursion_limit(bound, deps.settings.INGESTION_MAX_RETRIES),
        )
        payload = {
            "thread_id": thread,
            "source_file": source_file,
            "max_retries": deps.settings.INGESTION_MAX_RETRIES,
            "assembled": [],
            "skipped": [],
        }
        with tracing_scope(deps.settings):
            result = _stream(graph, payload, config, on_update, thread)
    except Exception:
        deps.runs.close(thread)
        raise
    return _close_when_finished(deps, thread, result)


def resume_ingestion(
    graph: CompiledStateGraph,
    deps: IngestionDeps,
    thread_id: str,
    choice: Choice,
    *,
    on_update: OnUpdate | None = None,
) -> RunResult:
    """Resume a paused run with `Command(resume=choice)` and the same `thread_id` (FR-153); the run
    config's metadata is rebuilt from the saved state (`source_file`, `document_sha`, `page_count`)
    and `limit = recursion_limit(len(tables), R)`. Same streaming, result and closing as
    `run_ingestion`. An unknown or finished `thread_id` raises `ValueError`."""
    try:
        deps.runs.get(thread_id)
    except KeyError:
        raise ValueError(f"Run {thread_id!r} is not open.") from None
    snapshot = graph.get_state({"configurable": {"thread_id": thread_id}})
    if not snapshot.interrupts:
        raise ValueError(f"Run {thread_id!r} is not paused.")
    try:
        values = dict(snapshot.values)
        tables = values.get("tables") or []
        config = run_config(
            deps.settings,
            source_file=values["source_file"],
            document_sha=values["document_sha"],
            pages=values["page_count"],
            thread_id=thread_id,
            limit=recursion_limit(len(tables), deps.settings.INGESTION_MAX_RETRIES),
        )
        with tracing_scope(deps.settings):
            result = _stream(graph, Command(resume=choice), config, on_update, thread_id)
    except Exception:
        deps.runs.close(thread_id)
        raise
    return _close_when_finished(deps, thread_id, result)
