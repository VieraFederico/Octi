"""The nodes of the ingestion graph (spec 01 §7 "Ingestion graph"): one small function per node.

Each node is `node(state, deps) -> dict`: it reads the state, calls one module of the agent, and
returns only the keys it changes (a partial update). `graph.py` binds `deps` and wires the edges.
A node that writes `outcome` ends the run. Contract: "Contract (Iteration 5)" in
`specs/01-ingestion-plan-artifacts/CONTEXT.md`.
"""

import json
import logging
from typing import Any

from langgraph.types import interrupt

from agents.ingestion.indexing import (
    TableToIndex,
    assemble_metadata,
    exceeds_size_guard,
    index_metadata,
    write_document,
)
from agents.ingestion.pdf.cleaning import dtype_name, rows_as_text
from agents.ingestion.pdf.context import collect_context as read_context
from agents.ingestion.pdf.document import open_document, pages_without_text, reported_image_pages
from agents.ingestion.pdf.tables import document_sha
from agents.ingestion.pdf.tables import extract_tables as read_tables
from agents.ingestion.prompts import ROWS_TO_LLM, build_messages
from agents.ingestion.schemas import TableContext, TableEnrichment, TableMetadata
from agents.ingestion.state import IngestionDeps, IngestionState
from agents.ingestion.validation import validate as check_answer
from services.errors import AppError, DocumentError, LLMProxyError
from services.llm import translate_proxy_errors

logger = logging.getLogger(__name__)

# Chat sentences (spec 01; BR-106: no service named, no feedback). `{file}` is the file name.
FAILED_ENRICH = "Something went wrong on my side and I couldn't index {file}. Your previous version is unchanged."  # FR-160
FAILED_INDEX = "Couldn't index {file}. Your previous version is unchanged."  # FR-139
PREVIOUS_NOT_REMOVED = (
    "{file} was indexed, but its previous version couldn't be fully removed. Upload it again to clean up."
)  # FR-140
NO_TABLES = "I didn't find any tables in {file}."  # FR-142
NOTHING_INDEXED = "I couldn't index any table from {file}."  # FR-142
CANCELLED = "Ingestion cancelled. Nothing from {file} was indexed."  # FR-120, FR-135 (S01-D-021)


def format_pages(pages: list[int]) -> str:
    """`page 3`, or `pages 4–5` for consecutive pages (en dash), or `pages 2, 5` otherwise."""
    if len(pages) == 1:
        return f"page {pages[0]}"
    consecutive = all(pages[index + 1] == pages[index] + 1 for index in range(len(pages) - 1))
    if consecutive:
        return f"pages {pages[0]}\u2013{pages[-1]}"
    return "pages " + ", ".join(str(page) for page in pages)


def load_pdf(state: IngestionState, deps: IngestionDeps) -> dict[str, Any]:
    """Open the run's PDF (FR-105 … FR-107) and read what extraction needs.

    Reads `deps.runs.get(thread_id).pdf`; `open_document` it and keep the document in
    `RunData.document`. Returns `document_sha` (`document_sha(pdf)`), `page_count`, `image_pages`
    (`reported_image_pages`) and one `no_text_pages` Skipped part per run of consecutive
    `pages_without_text`. On a `DocumentError` returns only
    `outcome = {"status": "failed", "message": exc.user_message}`.
    """
    run = deps.runs.get(state["thread_id"])
    try:
        document = open_document(run.pdf)
    except DocumentError as exc:
        return {"outcome": {"status": "failed", "message": exc.user_message}}
    run.document = document
    skipped = [
        {"kind": "no_text_pages", "pages": run_pages, "table_id": "", "caption": ""}
        for run_pages in _consecutive_runs(pages_without_text(document))
    ]
    update: dict[str, Any] = {
        "document_sha": document_sha(run.pdf),
        "page_count": document.page_count,
        "image_pages": reported_image_pages(document),
    }
    if skipped:
        update["skipped"] = skipped
    return update


def extract_tables(state: IngestionState, deps: IngestionDeps) -> dict[str, Any]:
    """Find the Tables (`pdf.tables.extract_tables(doc, document_sha)`), FR-109 … FR-119.

    Readable Tables: stored whole in `RunData.tables[table_id]`, and returned as `tables` (one
    `TableState` each, `context` None, `rows = rows_as_text(frame, ROWS_TO_LLM)`, `dtypes` by
    `dtype_name`). Unreadable ones: one `unreadable_table` Skipped part each. Also returns
    `current = 0`, `attempts = 0`, `feedback = []`, `answer = None`.
    """
    run = deps.runs.get(state["thread_id"])
    tables: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for extracted in read_tables(run.document, state["document_sha"]):
        if extracted.unreadable:
            skipped.append(
                {
                    "kind": "unreadable_table",
                    "pages": list(extracted.pages),
                    "table_id": extracted.table_id,
                    "caption": "",
                }
            )
            continue
        frame = extracted.frame
        assert frame is not None  # an unreadable table is skipped above and never has a frame
        run.tables[extracted.table_id] = extracted
        tables.append(
            {
                "table_id": extracted.table_id,
                "pages": list(extracted.pages),
                "columns": list(extracted.columns),
                "dtypes": [dtype_name(frame[name]) for name in extracted.columns],
                "hints": {name: list(hints) for name, hints in extracted.hints.items()},
                "row_headers": list(extracted.row_headers),
                "rows": rows_as_text(frame, ROWS_TO_LLM),
                "n_rows": len(frame),
                "context": None,
            }
        )
    update: dict[str, Any] = {
        "tables": tables,
        "current": 0,
        "attempts": 0,
        "feedback": [],
        "answer": None,
    }
    if skipped:
        update["skipped"] = skipped
    return update


def ask_unreadable(state: IngestionState, deps: IngestionDeps) -> dict[str, Any]:
    """Pause with the FR-119 question (`interrupt(PauseQuestion)`); resume value `continue` | `cancel`.

    intro `I couldn't read some parts of {file}:`; one bullet per `no_text_pages` part
    (`{format_pages} (no selectable text)`) and per `unreadable_table` part (`a table on page N`), in
    page order; question `They won't be indexed. Continue with the rest, or cancel?`; choices
    `[cancel "Cancel ingestion", continue "Continue"]`. `continue` → `{}`; `cancel` → `outcome`
    `cancelled` with `CANCELLED`. Any other value raises `ValueError`.
    """
    parts = [part for part in state["skipped"] if part["kind"] in ("no_text_pages", "unreadable_table")]
    bullets = []
    for part in sorted(parts, key=lambda part: part["pages"][0]):
        if part["kind"] == "no_text_pages":
            bullets.append(f"{format_pages(part['pages'])} (no selectable text)")
        else:
            bullets.append(f"a table on page {part['pages'][0]}")
    resume = interrupt(
        {
            "pause": "ask_unreadable",
            "intro": f"I couldn't read some parts of {state['source_file']}:",
            "bullets": bullets,
            "question": "They won't be indexed. Continue with the rest, or cancel?",
            "choices": [
                {"value": "cancel", "label": "Cancel ingestion"},
                {"value": "continue", "label": "Continue"},
            ],
        }
    )
    if resume == "continue":
        return {}
    if resume == "cancel":
        return {"outcome": {"status": "cancelled", "message": CANCELLED.format(file=state["source_file"])}}
    raise ValueError(f"Unexpected answer: {resume!r}")


def collect_context(state: IngestionState, deps: IngestionDeps) -> dict[str, Any]:
    """The Table context of every Table (`pdf.context.collect_context`), FR-123 … FR-126.

    Returns `tables` with each `context` set to the five `TableContext` fields as a dict.
    """
    run = deps.runs.get(state["thread_id"])
    tables = []
    for table_state in state["tables"]:
        context = read_context(run.document, run.tables[table_state["table_id"]])
        tables.append({**table_state, "context": _context_dict(context)})
    return {"tables": tables}


def enrich(state: IngestionState, deps: IngestionDeps) -> dict[str, Any]:
    """One LLM attempt for the current Table (FR-127 … FR-130, FR-160).

    `deps.make_chat_model(deps.settings).with_structured_output(TableEnrichment, include_raw=True)`,
    invoked inside `translate_proxy_errors()` with `build_messages(table, context, source_file,
    previous=state answer if feedback else None, feedback=feedback)`. `answer` = `parsed.model_dump()`
    when parsed, else the raw dict: `raw.tool_calls[0]["args"]` if tool calls, else `json.loads(raw.content)`
    when that is a JSON object, else `{}` (S01-D-015). Returns `attempts + 1` and `answer`.
    An `LLMProxyError` returns only `outcome` `failed` with `FAILED_ENRICH` (not a Skipped part).
    """
    run = deps.runs.get(state["thread_id"])
    current = state["tables"][state["current"]]
    feedback = state["feedback"]
    messages = build_messages(
        run.tables[current["table_id"]],
        TableContext(**current["context"]),
        state["source_file"],
        previous=state["answer"] if feedback else None,
        feedback=feedback,
    )
    model = deps.make_chat_model(deps.settings).with_structured_output(TableEnrichment, include_raw=True)
    try:
        with translate_proxy_errors():
            result = model.invoke(messages)
    except LLMProxyError:
        return {"outcome": {"status": "failed", "message": FAILED_ENRICH.format(file=state["source_file"])}}
    return {"attempts": state["attempts"] + 1, "answer": _answer_dict(result)}


def validate(state: IngestionState, deps: IngestionDeps) -> dict[str, Any]:
    """The five checks (`validation.validate`), then assembly and the size guard (FR-131 … FR-136, FR-141).

    Returns `feedback`. If it is empty: `assemble_metadata` + `index_metadata`; under the guard →
    `assembled` gets one item, over it → `skipped` gets a `table` part. If feedback remains and
    `attempts > max_retries` → `skipped` gets a `table` part. A skipped Table's last feedback goes to a
    DEBUG log only (BR-106). The `table` part's `caption` is the context's caption.
    """
    run = deps.runs.get(state["thread_id"])
    current = state["tables"][state["current"]]
    extracted = run.tables[current["table_id"]]
    feedback = check_answer(state["answer"], extracted)
    if not feedback:
        enrichment = TableEnrichment.model_validate(state["answer"])
        metadata = assemble_metadata(enrichment, extracted, state["source_file"])
        flat = index_metadata(metadata, extracted, state["document_sha"])
        if exceeds_size_guard(flat):
            return {"feedback": feedback, "skipped": [_table_part(current)]}
        return {
            "feedback": feedback,
            "assembled": [{"metadata": metadata.model_dump(mode="json"), "record_metadata": flat}],
        }
    if state["attempts"] > state["max_retries"]:
        logger.debug("Skipping table %s. Last feedback: %s", current["table_id"], " ".join(feedback))
        return {"feedback": feedback, "skipped": [_table_part(current)]}
    return {"feedback": feedback}


def next_table(state: IngestionState, deps: IngestionDeps) -> dict[str, Any]:
    """Move to the next Table: `current + 1`, `attempts = 0`, `feedback = []`, `answer = None` (FR-133)."""
    return {"current": state["current"] + 1, "attempts": 0, "feedback": [], "answer": None}


def ask_skipped(state: IngestionState, deps: IngestionDeps) -> dict[str, Any]:
    """Pause with the FR-134 question; resume value `index` | `cancel`.

    intro `There was a problem processing these tables in your PDF:`; one bullet per `table` Skipped
    part: `{format_pages}: {caption}`, or `{format_pages}` when the caption is empty. With N =
    len(assembled) ≥ 1: question `Index the other N tables, or cancel?` (`table` when N = 1), choices
    `[cancel "Cancel ingestion", index "Index N"]`; with N = 0: `No table could be processed. Cancel?`,
    choices `[cancel "Cancel ingestion"]`. `index` → `{}`; `cancel` → `outcome` `cancelled`.
    Any other value (also `index` when N = 0) raises `ValueError`.
    """
    bullets = []
    for part in state["skipped"]:
        if part["kind"] != "table":
            continue
        pages = format_pages(part["pages"])
        bullets.append(f"{pages}: {part['caption']}" if part["caption"] else pages)
    count = len(state["assembled"])
    if count >= 1:
        noun = "table" if count == 1 else "tables"
        question = f"Index the other {count} {noun}, or cancel?"
        choices: list[dict[str, str]] = [
            {"value": "cancel", "label": "Cancel ingestion"},
            {"value": "index", "label": f"Index {count}"},
        ]
    else:
        question = "No table could be processed. Cancel?"
        choices = [{"value": "cancel", "label": "Cancel ingestion"}]
    resume = interrupt(
        {
            "pause": "ask_skipped",
            "intro": "There was a problem processing these tables in your PDF:",
            "bullets": bullets,
            "question": question,
            "choices": choices,
        }
    )
    if resume == "index" and count >= 1:
        return {}
    if resume == "cancel":
        return {"outcome": {"status": "cancelled", "message": CANCELLED.format(file=state["source_file"])}}
    raise ValueError(f"Unexpected answer: {resume!r}")


def index(state: IngestionState, deps: IngestionDeps) -> dict[str, Any]:
    """Store the valid Tables (`indexing.write_document`), FR-137 … FR-142.

    No assembled Table: `no_tables` / `NO_TABLES` when no table was found at all, else
    `nothing_indexed` / `NOTHING_INDEXED` (some table was unreadable or skipped); no call is made.
    Otherwise one `TableToIndex(TableMetadata.model_validate(metadata), RunData.tables[id].frame,
    record_metadata)` per item, `write_document(settings, source_file, document_sha, items,
    embeddings=deps.embeddings, index=deps.index)`. Success → `indexed` with
    `Indexed N tables from {file}` (`table` when N = 1); `previous_removed=False` → `indexed` with
    `PREVIOUS_NOT_REMOVED`; any `AppError` → `failed` with `FAILED_INDEX` (never its user_message).
    """
    source_file = state["source_file"]
    assembled = state["assembled"]
    if not assembled:
        found = bool(state.get("tables")) or any(
            part["kind"] in ("unreadable_table", "table") for part in state.get("skipped", [])
        )
        if found:
            return {"outcome": {"status": "nothing_indexed", "message": NOTHING_INDEXED.format(file=source_file)}}
        return {"outcome": {"status": "no_tables", "message": NO_TABLES.format(file=source_file)}}
    run = deps.runs.get(state["thread_id"])
    items = []
    for item in assembled:
        metadata = TableMetadata.model_validate(item["metadata"])
        items.append(TableToIndex(metadata, run.tables[metadata.table_id].frame, item["record_metadata"]))
    try:
        result = write_document(
            deps.settings,
            source_file,
            state["document_sha"],
            items,
            embeddings=deps.embeddings,
            index=deps.index,
        )
    except AppError:
        return {"outcome": {"status": "failed", "message": FAILED_INDEX.format(file=source_file)}}
    if not result.previous_removed:
        return {"outcome": {"status": "indexed", "message": PREVIOUS_NOT_REMOVED.format(file=source_file)}}
    count = len(result.table_ids)
    noun = "table" if count == 1 else "tables"
    return {"outcome": {"status": "indexed", "message": f"Indexed {count} {noun} from {source_file}"}}


def _consecutive_runs(pages: list[int]) -> list[list[int]]:
    """Split `pages` into runs of consecutive numbers, keeping the order they arrived in."""
    runs: list[list[int]] = []
    for page in pages:
        if runs and page == runs[-1][-1] + 1:
            runs[-1].append(page)
        else:
            runs.append([page])
    return runs


def _context_dict(context: TableContext) -> dict[str, str]:
    """The five `TableContext` fields as a plain dict."""
    return {
        "section": context.section,
        "caption": context.caption,
        "before": context.before,
        "after": context.after,
        "footnotes": context.footnotes,
    }


def _answer_dict(result: dict[str, Any]) -> dict[str, Any]:
    """The parsed answer, or the raw JSON object the model returned when it did not parse."""
    if result["parsed"] is not None:
        return result["parsed"].model_dump()
    raw = result["raw"]
    if getattr(raw, "tool_calls", None):
        return raw.tool_calls[0]["args"]
    content = raw.content
    if isinstance(content, str):
        try:
            loaded = json.loads(content)
        except json.JSONDecodeError:
            return {}
        if isinstance(loaded, dict):
            return loaded
    return {}


def _table_part(table_state: dict[str, Any]) -> dict[str, Any]:
    """A `table` Skipped part. Its caption is the context's caption (empty when there is none)."""
    context = table_state.get("context") or {}
    return {
        "kind": "table",
        "pages": list(table_state["pages"]),
        "table_id": table_state["table_id"],
        "caption": context.get("caption", ""),
    }
