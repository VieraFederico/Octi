"""Ingestion as one durable assistant message with streaming status and pauses (D-065)."""

import html
import logging
from collections.abc import MutableMapping
from typing import Any
from uuid import uuid4

import streamlit as st

from agents.ingestion.graph import build_graph, run_ingestion, resume_ingestion
from agents.ingestion.indexing import entry_from_record
from agents.ingestion.nodes import PREVIOUS_NOT_REMOVED, format_pages
from agents.ingestion.state import make_deps
from ui.catalog import SETTINGS, open_library, update_catalog
from ui.table_card import render_table_card

ACTIVE = "active-ingestion"
RUNTIME = "ingestion-runtime"
BUSY_HINT = "Answer the question above first."
logger = logging.getLogger(__name__)


def queue_run(state: MutableMapping[str, Any], upload: dict[str, Any]) -> None:
    """Keep bytes outside the message; the graph moves them into its per-run store."""
    message = {"role": "assistant", "content": "", "kind": "ingestion", "thread_id": uuid4().hex,
               "source_file": upload["name"], "status": "queued", "lines": [], "entries": [],
               "skipped": [], "image_pages": [], "question": None, "text": upload.get("text", ""),
               "progress": {"max_retries": state[SETTINGS].INGESTION_MAX_RETRIES}}
    state.setdefault("messages", []).append(message)
    state[ACTIVE] = message
    state["ingestion-pdf"] = upload["pdf"]


def is_busy(state: MutableMapping[str, Any]) -> bool:
    return bool(state.get(ACTIVE))


def is_streaming(state: MutableMapping[str, Any]) -> bool:
    active = state.get(ACTIVE)
    return bool(active and (active["status"] in ("queued", "running") or active.get("resume")))


def abandon_run(state: MutableMapping[str, Any]) -> None:
    """New chat at a pause discards the in-memory graph and closes its document."""
    active = state.pop(ACTIVE, None)
    runtime = state.pop(RUNTIME, None)
    if active and runtime:
        runtime[1].runs.close(active["thread_id"])
    state.pop("ingestion-pdf", None)
    state.pop("pending-upload", None)
    state.pop("upload-confirming", None)


def status_line(node: str, values: dict[str, Any], source_file: str) -> str:
    """Translate light graph facts into the FR-144 status lines, without feedback."""
    tables = values.get("tables", [])
    if node == "load_pdf" and "page_count" in values:
        count = values["page_count"]
        return f"Opened {source_file} ({count} {'page' if count == 1 else 'pages'})"
    if node == "extract_tables":
        pages = ", ".join(format_pages(t["pages"]).removeprefix("pages ").removeprefix("page ") for t in tables)
        suffix = f" (pages {pages})" if pages else ""
        return f"Found {len(tables)} {'table' if len(tables) == 1 else 'tables'}{suffix}"
    if node == "collect_context":
        return "Collected context"
    if node == "enrich":
        return (f"Describing table {values.get('current', 0) + 1} of {len(tables)} "
                f"(attempt {values.get('attempts', 1)} of {values.get('max_retries', 2) + 1})…")
    if node == "validate":
        return "Checked table description"
    if node == "next_table":
        return "Moving to the next table"
    if node in ("ask_unreadable", "ask_skipped"):
        return "Recorded your choice"
    if node == "index" and values.get("outcome", {}).get("status") == "indexed":
        count = len(values.get("assembled", []))
        return f"Indexed {count} {'table' if count == 1 else 'tables'}"
    return values.get("outcome", {}).get("message", "")


def _run(message: dict[str, Any], box: Any) -> None:
    """Start or resume in this script; a rerun redraws enabled controls after it stops."""
    state = st.session_state
    message["status"] = "running"

    def on_update(node: str, update: dict[str, Any]) -> None:
        # Reducer fields append; other light facts replace, matching the graph contract.
        progress = message["progress"]
        for key, value in update.items():
            if key in ("assembled", "skipped"):
                progress.setdefault(key, []).extend(value)
            elif key not in ("answer", "feedback"):
                progress[key] = value
        line = status_line(node, progress, message["source_file"])
        if line:
            message["lines"].append(line)
            with box:
                st.text(line)

    try:
        if RUNTIME not in state:
            deps = make_deps(state[SETTINGS])
            state[RUNTIME] = (build_graph(deps), deps)
        graph, deps = state[RUNTIME]
        choice = message.pop("resume", None)
        if choice:
            result = resume_ingestion(graph, deps, message["thread_id"], choice, on_update=on_update)
        else:
            pdf = state.pop("ingestion-pdf")
            result = run_ingestion(graph, deps, message["source_file"], pdf,
                                   thread_id=message["thread_id"], on_update=on_update)
        message["thread_id"] = result.thread_id
        message["status"] = result.status
        message["question"] = result.question
        if result.status == "finished":
            values = result.values
            outcome = values["outcome"]
            message["content"] = outcome["message"]
            message["outcome"] = outcome["status"]
            message["skipped"] = values.get("skipped", [])
            message["image_pages"] = values.get("image_pages", [])
            if outcome["status"] == "indexed":
                message["entries"] = [entry_from_record(item["record_metadata"]) for item in values["assembled"]]
                update_catalog(state, message["entries"], previous_removed=(
                    outcome["message"] != PREVIOUS_NOT_REMOVED.format(file=message["source_file"])))
            state.pop(ACTIVE, None)
            message.pop("progress", None)
    except Exception:
        # A UI boundary must not expose raw service errors, even during client construction.
        logger.debug("Ingestion UI run failed", exc_info=True)
        runtime = state.pop(RUNTIME, None)
        if runtime:
            runtime[1].runs.close(message["thread_id"])
        state.pop("ingestion-pdf", None)
        state.pop(ACTIVE, None)
        message.update(status="finished", outcome="failed", question=None,
                       content=f"Something went wrong on my side and I couldn't index {message['source_file']}. Your previous version is unchanged.")
        message.pop("progress", None)
    st.rerun()


def _choose(message: dict[str, Any], choice: str) -> None:
    message["resume"] = choice


def render_run_message(message: dict[str, Any]) -> None:
    """Called inside its chat message, both while active and on every later rerun."""
    finished = message["status"] == "finished"
    label = message["content"] if finished else f"Ingesting {message['source_file']}"
    box = st.status(label, expanded=not finished, state="error" if message.get("outcome") == "failed" else "complete" if finished else "running")
    with box:
        for line in message["lines"]:
            st.text(line)
    if message["status"] in ("queued", "running") or message.get("resume"):
        _run(message, box)
    if message["status"] == "paused":
        question = message["question"]
        st.text(question["intro"])
        for bullet in question["bullets"]:
            st.html(f"<div style='overflow-wrap:anywhere'>• {html.escape(bullet)}</div>")
        st.text(question["question"])
        for choice in question["choices"]:
            st.button(choice["label"], key=f"ingestion-{message['thread_id']}-{choice['value']}",
                      on_click=_choose, args=(message, choice["value"]))
    if finished:
        for entry in message["entries"]:
            render_table_card(entry)
        if message["skipped"]:
            st.text("Skipped parts:")
            for part in message["skipped"]:
                text = format_pages(part["pages"])
                if part["kind"] == "no_text_pages":
                    text += " (no selectable text)"
                elif part["kind"] == "unreadable_table":
                    text = "a table on " + text
                elif part.get("caption"):
                    text += ": " + part["caption"]
                st.html(f"<div style='overflow-wrap:anywhere'>• {html.escape(text)}</div>")
        pages = message["image_pages"]
        if pages:
            page_text = ", ".join(map(str, pages[:-1])) + f" and {pages[-1]}" if len(pages) > 1 else str(pages[0])
            st.text(f"Pages {page_text} contain images. If any of them shows a table, I couldn't read it.")
        st.button("Open in library", key=f"ingestion-{message['thread_id']}-library",
                  on_click=open_library, args=(st.session_state, message["source_file"]))
        if message["text"]:
            from ui.chat import QUESTION_PLACEHOLDER
            st.markdown(QUESTION_PLACEHOLDER)
