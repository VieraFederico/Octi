"""One durable Analysis chat message: progress, answer, missing parts and folded evidence."""

import html
import json
import logging
from collections.abc import MutableMapping
from typing import Any
from uuid import uuid4

import streamlit as st

from agents.analyst.graph import CONFIRMATION_REQUEST, resume_analysis, run_analysis
from agents.analyst.nodes import OUTAGE_MESSAGE, selected_tables
from agents.analyst.state import make_deps
from services.errors import TableStoreError
from services.table_store import read_table
from ui.analysis_window import build_window
from ui.catalog import CATALOG, LOADED, SETTINGS
from ui.table_card import render_table_card

ACTIVE = "active-analysis"
CONFIRM_TABLES = "confirm-tables"  # session key of the toggle's value; on by default (spec 03 FR-319)
TOGGLE_LABEL = "Confirm tables before calculating"
PAUSE_INTRO = "Before I calculate, check the tables I picked:"
WAITING_LINE = "Waiting for your confirmation"
BADGE_COLORS = {"answered": "#a6e3a1", "partial": "#fab387", "cannot_answer": "#f38ba8"}
logger = logging.getLogger(__name__)


def new_message(question: str) -> dict[str, Any]:
    return {"role": "assistant", "content": "", "kind": "analysis", "question": question,
            "thread_id": uuid4().hex, "status": "queued", "lines": [], "values": {}}


def queue_analysis(state: MutableMapping[str, Any], question: str) -> None:
    message = new_message(question)
    state.setdefault("messages", []).append(message)
    state[ACTIVE] = message


def is_busy(state: MutableMapping[str, Any]) -> bool:
    active = state.get(ACTIVE)
    return bool(active and active.get("status") in ("queued", "running"))


def is_paused(state: MutableMapping[str, Any]) -> bool:
    """The active run waits for the table confirmation: the composer waits too, the sidebar does not."""
    active = state.get(ACTIVE)
    return bool(active and active.get("status") == "paused")


def render_confirm_toggle() -> None:
    """The session-long toggle; its value is kept under its own key so other views do not reset it."""
    state = st.session_state
    state[CONFIRM_TABLES] = st.toggle(TOGGLE_LABEL, value=state.get(CONFIRM_TABLES, True))


def status_line(node: str, values: dict[str, Any], max_retries: int) -> str:
    plan = values.get("plan")
    if node == "library_check" and not values.get("answer"):
        return "Understanding the question…"
    if node == "understand" and plan is not None:
        return f"Understood as: {plan.standalone_question}"
    if node == "retrieve" and plan is not None:
        return f"Searching the library ({len(plan.search_phrases)} searches)…"
    if node == "select" and values.get("selection") is not None:
        ids = {table_id for part in values["selection"].parts if part.verdict == "answerable" for table_id in part.table_ids}
        return f"Selected {len(ids)} tables"
    if node == "generate_code":
        return f"Running the calculation (attempt {values.get('code_attempts', 1)} of {max_retries + 1})…"
    if node == "merge_status":
        return "Writing the answer…"
    return ""


def _run(message: dict[str, Any], box: Any) -> None:
    state = st.session_state
    message["status"] = "running"
    settings = state[SETTINGS]

    def on_update(node: str, update: dict[str, Any]) -> None:
        message["values"].update(update)
        line = status_line(node, message["values"], settings.ANALYST_MAX_RETRIES)
        if line:
            message["lines"].append(line)
            with box:
                st.text(line)

    reply = message.pop("reply", None)
    try:
        deps = make_deps(settings, catalog=state.get(CATALOG, []) if state.get(LOADED) else None)
        if reply is None:
            values = run_analysis(message["question"], build_window(state["messages"]), deps,
                                  state.get(CONFIRM_TABLES, True), on_update=on_update, thread_id=message["thread_id"])
        else:
            values = resume_analysis(message["thread_id"], reply, deps, on_update=on_update)
        message["values"] = values
        message["content"] = values.get("answer") or OUTAGE_MESSAGE
    except Exception:
        logger.debug("Analysis UI run failed", exc_info=True)
        message["values"] = {"error": {"kind": "llm", "message": OUTAGE_MESSAGE},
                             "answer_status": "cannot_answer", "answer": OUTAGE_MESSAGE}
        message["content"] = OUTAGE_MESSAGE
    request = message["values"].get(CONFIRMATION_REQUEST)
    if request is not None:
        message.update(status="paused", pause=request, content="")
        message["lines"].append(WAITING_LINE)
    else:
        message["status"] = "finished"
        state.pop(ACTIVE, None)
    st.rerun()


def _pages(pages: list[int]) -> str:
    return f"page {pages[0]}" if len(pages) == 1 else "pages " + ", ".join(str(page) for page in pages)


def _resume_with(message: dict[str, Any], reply: dict[str, Any]) -> None:
    message.update(status="running", reply=reply)
    message.pop("pause", None)
    st.rerun()


def _render_pause(message: dict[str, Any]) -> None:
    """Per Question part: Candidate tables as boxes (the Selected ones ticked) or the part's reason."""
    thread_id = message["thread_id"]
    st.markdown(PAUSE_INTRO)
    tables: dict[int, list[str]] = {}
    for part in message["pause"]["parts"]:
        st.markdown(f"**Question {part['number']}**")
        st.text(part["text"])
        if not part["answerable"]:
            st.text(part["reason"])
            continue
        tables[part["number"]] = [
            candidate["table_id"] for candidate in part["candidates"]
            if st.checkbox(f"{candidate['name']} ({candidate['document']}, {_pages(candidate['pages'])})",
                           value=candidate["table_id"] in part["selected"],
                           key=f"confirm-{thread_id}-{part['number']}-{candidate['table_id']}")
        ]
    cancel, calculate = st.columns(2)
    if cancel.button("Cancel", key=f"confirm-cancel-{thread_id}"):
        _resume_with(message, {"action": "cancel"})
    if calculate.button("Calculate", key=f"confirm-calculate-{thread_id}", type="primary"):
        _resume_with(message, {"action": "calculate", "tables": tables})


@st.cache_data(show_spinner=False)
def _full_table(thread_id: str, table_id: str):
    """Full frames stay in Streamlit's cache, never the message or graph state."""
    return read_table(table_id)


def _tables(message: dict[str, Any], considered: bool) -> None:
    values = message["values"]
    tables = selected_tables(values, answerable_only=not considered)
    if considered and not tables:
        tables = values.get("candidates", [])[:3]
    with st.expander("Tables considered" if considered else "Tables used"):
        for entry in tables:
            render_table_card(entry)
            key = f"analysis-data-{message['thread_id']}-{entry.table_id}"
            data_box = st.expander("Show data", key=key, on_change="rerun")
            if data_box.open:
                with data_box:
                    try:
                        st.dataframe(_full_table(message["thread_id"], entry.table_id), width="stretch")
                    except TableStoreError:
                        st.error("Couldn't load this table's data. Please try again in a moment.")


def render_analysis_message(message: dict[str, Any]) -> None:
    """Render inside st.chat_message; reruns retain the same message and evidence."""
    finished = message["status"] == "finished"
    values = message["values"]
    box = st.status("Analysis complete" if finished else "Analyzing your question…", expanded=not finished,
                    state="error" if values.get("error") else "complete" if finished else "running")
    with box:
        for line in message["lines"]:
            st.text(line)
    if message["status"] == "paused":
        _render_pause(message)
        return
    if not finished:
        _run(message, box)
    if values.get("error"):
        st.error(OUTAGE_MESSAGE)
        return
    status = values["answer_status"]
    st.html(f'<span style="display:inline-block;border-radius:0.5rem;padding:0.2rem 0.6rem;'
            f'background:{BADGE_COLORS[status]};color:#1e1e2e">{html.escape(status)}</span>')
    st.markdown(message["content"])
    for part in values.get("part_outcomes", []):
        if part.outcome != "answered":
            st.text(f"Missing: Question {part.part}: {part.reason}")
    considered = values.get("code_attempts", 0) == 0
    _tables(message, considered)
    if considered:
        return
    history = values.get("attempts_history", [])
    draft = values.get("code_draft")
    with st.expander("Code"):
        st.code(history[-1]["code"] if history else draft.code if draft is not None else "", language="python")
    with st.expander("Output"):
        result = values.get("sandbox_result") or {}
        stdout = result.get("stdout", "")
        st.code(stdout, language="text")
        try:
            emitted = json.loads(next(line for line in reversed(stdout.splitlines()) if line.strip()))
        except (StopIteration, json.JSONDecodeError):
            emitted = None
        if isinstance(emitted, dict) and isinstance(emitted.get("parts"), list):
            st.json(emitted)
    with st.expander("Attempts"):
        for number, attempt in enumerate(history, start=1):
            if attempt["failure"]:
                st.text(f"Attempt {number}: {attempt['failure']}")
                st.code(attempt["code"], language="python")
                st.code(attempt["feedback"], language="text")
