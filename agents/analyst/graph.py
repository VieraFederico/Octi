"""Analyst StateGraph, bounded routing, streaming entry point and public-API tracing.

LangSmith Client masking covers every traced state payload, not only the execute node (D-121).
An explicit root trace receives completion metadata through RunTree.add_metadata (A-204).
"""

import re
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager, nullcontext
from dataclasses import asdict, is_dataclass
from typing import Any
from uuid import uuid4

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from langsmith import trace
from langsmith.run_helpers import get_current_run_tree, tracing_context
from pydantic import BaseModel

from agents.analyst import nodes
from agents.analyst.schemas import Turn
from agents.analyst.state import AnalystDeps, AnalystState
from services.settings import Settings
from services.tracing import make_langsmith_client

OnUpdate = Callable[[str, dict[str, Any]], None]
NODE_NAMES = ("library_check", "no_tables", "understand", "retrieve", "select", "confirm_tables",
              "generate_code", "execute", "check", "merge_status", "respond", "template", "fail")
CONFIRMATION_REQUEST = "confirmation_request"  # set on the returned state while the run waits for the user
# One saver for every run: a paused run's checkpoint must outlive the Streamlit rerun that started it.
CHECKPOINTER = InMemorySaver()


def mask_sandbox_output(payload: dict) -> dict:
    """A nonmutating Client hide_inputs/hide_outputs hook: raw output becomes byte sizes.

    Recurse through saved state, history and serialized models. Retry feedback copied from stderr
    is masked in history and in the trace copy of code prompts; the actual model input is intact.
    """
    def mask(value: Any) -> Any:
        if isinstance(value, BaseModel):
            return mask(value.model_dump(mode="json"))
        if is_dataclass(value) and not isinstance(value, type):
            return mask(asdict(value))
        if isinstance(value, dict):
            result = {}
            has_output = "stdout" in value or "stderr" in value
            for key, item in value.items():
                if key in ("stdout", "stderr") and isinstance(item, str):
                    result[f"{key}_bytes"] = len(item.encode("utf-8"))
                elif key == "feedback" and has_output and isinstance(item, str):
                    result["feedback_chars"] = len(item)
                else:
                    result[key] = mask(item)
            return result
        if isinstance(value, (list, tuple)):
            return [mask(item) for item in value]
        if isinstance(value, str) and "# Previous attempt\n" in value:
            return re.sub(r"(# Feedback to fix\n)(.*?)(# Task\n)",
                lambda match: f"{match[1]}[feedback masked: {len(match[2])} characters]\n\n{match[3]}", value, flags=re.DOTALL)
        return value

    return mask(payload)


def execution_metrics(result: dict[str, Any]) -> dict[str, Any]:
    return {"exit_code": result["exit_code"], "timed_out": result["timed_out"],
            "stdout_bytes": len(result["stdout"].encode("utf-8")),
            "stderr_bytes": len(result["stderr"].encode("utf-8"))}


def end_metadata(state: AnalystState) -> dict[str, Any]:
    plan = state.get("plan")
    error = state.get("error")
    return {"answer_status": state.get("answer_status"), "parts_total": len(plan.parts) if plan is not None else 0,
            "parts_answered": sum(part.outcome == "answered" for part in state.get("part_outcomes", [])),
            "attempts": state.get("code_attempts", 0), "selected_tables": len(nodes.selected_tables(state)),
            "error_kind": error["kind"] if error is not None else None,
            "confirmation": state.get("confirmation") or "skipped"}


def run_config(settings: Settings, question: str, window: Sequence[Turn], thread_id: str,
               extra_tags: Sequence[str] = ()) -> RunnableConfig:
    """FR-239 start labels; recursion is bounded above the longest valid retry route."""
    return {"run_name": f"Analysis: {question[:60]}", "tags": ["analysis", *extra_tags],
            "metadata": {"llm_model": settings.LLM_MODEL, "max_retries": settings.ANALYST_MAX_RETRIES,
                         "thread_id": thread_id, "window_turns": min(len(window), nodes.WINDOW_TURNS)},
            "configurable": {"thread_id": thread_id}, "run_id": uuid4(),
            "recursion_limit": 20 + 3 * (settings.ANALYST_MAX_RETRIES + 1)}


@contextmanager
def tracing_scope(settings: Settings, client: Any = None) -> Iterator[Any]:
    """Settings controls tracing, including when environment variables are omitted (FR-154)."""
    if not settings.LANGSMITH_TRACING:
        with tracing_context(enabled=False):
            yield None
        return
    client = client if client is not None else make_langsmith_client(
        settings, hide_inputs=mask_sandbox_output, hide_outputs=mask_sandbox_output,
    )
    with tracing_context(enabled=True, project_name=settings.LANGSMITH_PROJECT, client=client):
        yield client


def _bind(name: str, deps: AnalystDeps) -> Callable[[AnalystState], dict[str, Any]]:
    def bound(state: AnalystState) -> dict[str, Any]:
        update = getattr(nodes, name)(state, deps)
        if name == "execute" and update.get("sandbox_result") is not None:
            run = get_current_run_tree()
            if run is not None:
                run.add_metadata(execution_metrics(update["sandbox_result"]))
        return update
    return bound


def _after(state: AnalystState, target: str) -> str:
    return "fail" if state.get("error") else target


def route_after_library(state: AnalystState) -> str:
    return _after(state, "no_tables" if state.get("answer") == nodes.NO_TABLES_MESSAGE else "understand")


def route_after_select(state: AnalystState) -> str:
    if state.get("error"):
        return "fail"
    if state["selection_feedback"] and state["selection_attempts"] <= nodes.SELECTION_RETRIES:
        return "select"
    return "confirm_tables" if _any_answerable(state) else "merge_status"


def _any_answerable(state: AnalystState) -> bool:
    selection = state["selection"]
    return selection is not None and any(part.verdict == "answerable" for part in selection.parts)


def route_after_confirm(state: AnalystState) -> str:
    """Cancel, or no table left for any part, skips code generation (spec 03 FR-317, FR-318)."""
    return "generate_code" if _any_answerable(state) else "merge_status"


def route_after_generate(state: AnalystState) -> str:
    return _after(state, "execute" if nodes.valid_draft(state) else "check")


def build_graph(deps: AnalystDeps) -> CompiledStateGraph:
    """The Analyst graph; `confirm_tables` may pause after `select`, so runs are checkpointed."""
    builder = StateGraph(AnalystState)
    for name in NODE_NAMES:
        builder.add_node(name, _bind(name, deps))
    builder.add_edge(START, "library_check")
    builder.add_conditional_edges("library_check", route_after_library, ["fail", "no_tables", "understand"])
    builder.add_conditional_edges("understand", lambda state: _after(state, "retrieve"), ["fail", "retrieve"])
    builder.add_conditional_edges("retrieve", lambda state: _after(state, "select"), ["fail", "select"])
    builder.add_conditional_edges("select", route_after_select, ["fail", "select", "confirm_tables", "merge_status"])
    builder.add_conditional_edges("confirm_tables", route_after_confirm, ["generate_code", "merge_status"])
    builder.add_conditional_edges("generate_code", route_after_generate, ["fail", "execute", "check"])
    builder.add_conditional_edges("execute", lambda state: _after(state, "check"), ["fail", "check"])
    builder.add_conditional_edges("check", lambda state: "generate_code" if state["last_failure"] is not None
        and state["code_attempts"] <= deps.settings.ANALYST_MAX_RETRIES else "merge_status", ["generate_code", "merge_status"])
    builder.add_edge("merge_status", "respond")
    builder.add_conditional_edges("respond", lambda state: END if state.get("answer") else "template", [END, "template"])
    for name in ("no_tables", "template", "fail"):
        builder.add_edge(name, END)
    return builder.compile(checkpointer=CHECKPOINTER)


def run_analysis(
    question: str, window: Sequence[Turn], deps: AnalystDeps, confirm_tables: bool, *,
    on_update: OnUpdate | None = None, thread_id: str | None = None, extra_tags: Sequence[str] = (),
) -> AnalystState:
    """Stream node updates, return the state; dependencies and raw table data stay outside it.

    With `confirm_tables` the run may stop after `select`: the returned state then holds
    `CONFIRMATION_REQUEST` (the pause payload) and `resume_analysis` continues the same thread.
    """
    state: AnalystState = {"question": question, "window": list(window[-nodes.WINDOW_TURNS:]),
        "plan": None, "candidates": [], "selection": None, "selection_attempts": 0, "selection_feedback": [],
        "code_attempts": 0, "code_draft": None, "sandbox_result": None, "last_failure": None,
        "attempts_history": [], "part_outcomes": [], "answer_status": None, "answer": None, "error": None,
        "confirmation": None if confirm_tables else "skipped"}
    return _stream(deps, dict(state), state, thread_id or uuid4().hex, on_update, extra_tags)


def resume_analysis(
    thread_id: str, reply: dict[str, Any], deps: AnalystDeps, *,
    on_update: OnUpdate | None = None, extra_tags: Sequence[str] = (),
) -> AnalystState:
    """Continue a paused run with the user's reply: `{"action": "calculate", "tables": {part: [ids]}}`
    or `{"action": "cancel"}`. An unknown action, or a thread that is not paused, raises `ValueError`."""
    if reply.get("action") not in ("calculate", "cancel"):
        raise ValueError(f"Unknown confirmation action {reply.get('action')!r}.")
    snapshot = build_graph(deps).get_state({"configurable": {"thread_id": thread_id}})
    if not snapshot.interrupts:
        raise ValueError(f"Analysis {thread_id!r} is not waiting for a confirmation.")
    return _stream(deps, Command(resume=reply), dict(snapshot.values), thread_id, on_update, extra_tags)


def abandon_analysis(thread_id: str) -> None:
    """Drop a paused run's checkpoint (New chat while it waits)."""
    CHECKPOINTER.delete_thread(thread_id)


def _stream(deps: AnalystDeps, payload: Any, state: AnalystState, thread_id: str,
            on_update: OnUpdate | None, extra_tags: Sequence[str]) -> AnalystState:
    """One graph call inside its own root trace; a finished run's checkpoint is dropped."""
    question = state["question"]
    config = run_config(deps.settings, question, state["window"], thread_id, extra_tags)
    graph = build_graph(deps)
    with tracing_scope(deps.settings, deps.tracing_client) as client:
        root_scope = trace(config["run_name"], inputs={"question": question, "window_turns": len(state["window"])},
            tags=config["tags"], metadata=config["metadata"], run_id=config["run_id"],
            project_name=deps.settings.LANGSMITH_PROJECT, client=client) if client is not None else nullcontext(None)
        with root_scope as root:
            # The root has the FR-239 name/id; the compiled graph is its child with a separate id.
            graph_config = {**config, "run_name": "Analyst graph", "run_id": uuid4()}
            for chunk in graph.stream(payload, graph_config, stream_mode="updates"):
                for name, update in chunk.items():
                    if name != "__interrupt__" and update is not None:
                        state.update(update)
                        if on_update is not None:
                            on_update(name, update)
            interrupts = graph.get_state(graph_config).interrupts
            if interrupts:
                state[CONFIRMATION_REQUEST] = interrupts[0].value
            else:
                state.pop(CONFIRMATION_REQUEST, None)
                CHECKPOINTER.delete_thread(thread_id)
            if root is not None:
                root.add_metadata(end_metadata(state))
                root.end(outputs=dict(state))
    return state
