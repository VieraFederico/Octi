"""End-to-end ingestion runs (spec 01 VC-123, VC-124, VC-134 … VC-137, VC-145, VC-147, VC-159).

The graph is driven only through `build_graph`, `run_ingestion` and `resume_ingestion`. Resume uses
the same graph object: its in-memory checkpointer is created in `build_graph`.
"""

from pathlib import Path

import pymupdf
import pytest
from langchain_core.messages import HumanMessage

from agents.ingestion.graph import build_graph, resume_ingestion, run_ingestion
from agents.ingestion.pdf.document import open_document, pages_without_text
from agents.ingestion.pdf.tables import document_sha, extract_tables
from agents.ingestion.schemas import ExtractedTable, TableEnrichment
from agents.ingestion.state import IngestionDeps, PauseQuestion, RunResult
from services.settings import Settings
from tests.pdf_fixtures import Page, image_only_page, make_pdf, paragraph, table, text_page
from tests.stubs import (
    FAKE_LANGSMITH_KEY,
    FAKE_LITELLM_KEY,
    FAKE_PINECONE_KEY,
    FakeEmbeddings,
    FakePineconeIndex,
    ScriptedChatModel,
    enrichment_for,
    invalid_enrichment,
)

SOURCE_FILE = "report.pdf"
# format_pages joins a consecutive run with an en dash (U+2013).
NO_TEXT_BULLET = "pages 2\u20133 (no selectable text)"
REPLACEMENT = "\ufffd"
PREVIOUS_ID = "previous-report"
PREVIOUS_METADATA = {"source_file": SOURCE_FILE, "table_id": PREVIOUS_ID, "name": "Previous version"}
SECRETS = (FAKE_LITELLM_KEY, FAKE_PINECONE_KEY, FAKE_LANGSMITH_KEY)

CANCEL_CHOICE = {"value": "cancel", "label": "Cancel ingestion"}
CONTINUE_CHOICE = {"value": "continue", "label": "Continue"}
UNREADABLE_INTRO = f"I couldn't read some parts of {SOURCE_FILE}:"
UNREADABLE_QUESTION = "They won't be indexed. Continue with the rest, or cancel?"
SKIPPED_INTRO = "There was a problem processing these tables in your PDF:"
CANCELLED_MESSAGE = f"Ingestion cancelled. Nothing from {SOURCE_FILE} was indexed."
NO_TABLES_MESSAGE = f"I didn't find any tables in {SOURCE_FILE}."
NOTHING_INDEXED_MESSAGE = f"I couldn't index any table from {SOURCE_FILE}."


def readable_tables(pdf: bytes) -> list[ExtractedTable]:
    """Readable Tables of a fixture PDF, in reading order."""
    with open_document(pdf) as doc:
        extracted = extract_tables(doc, document_sha(pdf))
    return [item for item in extracted if not item.unreadable]


def all_tables(pdf: bytes) -> list[ExtractedTable]:
    """Every Table extraction returns, including unreadable ones."""
    with open_document(pdf) as doc:
        return extract_tables(doc, document_sha(pdf))


def open_run(
    settings: Settings, answers: list[TableEnrichment]
) -> tuple[object, IngestionDeps, ScriptedChatModel, FakePineconeIndex]:
    """Deps and the graph. `make_chat_model` is the scripted factory, called with settings by enrich."""
    scripted = ScriptedChatModel(answers)
    index = FakePineconeIndex()
    deps = IngestionDeps(
        settings=settings,
        embeddings=FakeEmbeddings(),
        index=index,
        make_chat_model=scripted.build,
    )
    return build_graph(deps), deps, scripted, index


def files_in(folder: Path) -> list[str]:
    """Stems of the Table store files (the table ids), or [] when nothing has been written."""
    return sorted(path.stem for path in folder.iterdir()) if folder.exists() else []


def human_text(messages: list) -> str:
    """The table's own human message (the last one).

    The system prompt always contains the words "Feedback to fix" and "previous answer", so a retry
    is visible only on this message.
    """
    message = messages[-1]
    assert isinstance(message, HumanMessage)
    content = message.content
    return content if isinstance(content, str) else str(content)


def all_message_text(scripted: ScriptedChatModel) -> str:
    """Every message the stub recorded, in call order."""
    parts: list[str] = []
    for messages in scripted.calls:
        for message in messages:
            content = message.content
            parts.append(content if isinstance(content, str) else str(content))
    return "\n".join(parts)


def indexed_message(count: int) -> str:
    """Success sentence from `index`: "table" when one Table was stored, "tables" otherwise.

    No final period: the node docstring, S01-D-021 and FR-144 write it that way.
    """
    noun = "table" if count == 1 else "tables"
    return f"Indexed {count} {noun} from {SOURCE_FILE}"


def patch_replacement_cells(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rewrite cells marked GARBLED as ``�`` when PyMuPDF reads them (S01-D-010).

    PyMuPDF's HTML engine cannot draw text that extracts as ``�``. Two replacement characters in
    each marked cell, as in the table-level check: 4 of 6 filled cells are then unreadable.
    """
    real_extract = pymupdf.table.Table.extract

    def garbled_extract(self: pymupdf.table.Table) -> list[list[str | None]]:
        rows = real_extract(self)
        return [[cell.replace("GARBLED", "\ufffd\ufffd") if cell else cell for cell in row] for row in rows]

    monkeypatch.setattr(pymupdf.table.Table, "extract", garbled_extract)


def plant_previous(index: FakePineconeIndex, namespace: str) -> None:
    """A record left by an earlier ingestion of report.pdf. `put` itself is not an index call."""
    index.put(namespace, PREVIOUS_ID, PREVIOUS_METADATA)


def require_pause(result: RunResult, deps: IngestionDeps) -> PauseQuestion:
    """The question waiting at a pause. The per-run store stays open until the run ends."""
    assert result.status == "paused"
    assert result.question is not None
    assert result.thread_id in deps.runs.thread_ids()
    return result.question


def pdf_image_gap() -> bytes:
    """Four pages: a table on page 1, image-only pages 2 and 3, prose on page 4."""
    return make_pdf(
        Page(blocks=(table(["Region", "Sales"], [["North", "10"], ["South", "12"]]),)),
        image_only_page(),
        image_only_page(shade=180),
        text_page("Closing notes."),
    )


def pdf_one_table() -> bytes:
    return make_pdf(Page(blocks=(table(["Region", "Sales"], [["North", "10"], ["South", "12"]]),)))


def pdf_two_tables() -> bytes:
    return make_pdf(
        Page(
            blocks=(
                table(["Region", "Sales"], [["North", "10"], ["South", "12"]]),
                paragraph("Between the two tables."),
                table(["Product", "Units"], [["Pens", "5"], ["Ink", "7"]]),
            )
        )
    )


def pdf_three_tables() -> bytes:
    """Three Tables. The one on page 2 carries the caption "Table 2. Regional sales"."""
    return make_pdf(
        Page(blocks=(table(["Region", "Sales"], [["North", "10"], ["South", "12"]]),)),
        Page(
            blocks=(
                paragraph("Table 2. Regional sales"),
                table(["Quarter", "Units"], [["Q1", "4"], ["Q2", "5"]]),
            )
        ),
        Page(blocks=(table(["Product", "Stock"], [["Pens", "5"], ["Ink", "7"]]),)),
    )


def pdf_with_unreadable_table() -> bytes:
    """Page 1 readable; page 2 a table whose data cells are marked GARBLED."""
    readable = table(["Region", "Sales"], [["North", "10"], ["South", "12"]])
    garbled = table(["Region", "Sales"], [["GARBLED", "GARBLED"], ["GARBLED", "GARBLED"]])
    return make_pdf(Page(blocks=(readable,)), Page(blocks=(garbled,)))


def pdf_only_unreadable() -> bytes:
    """One page of prose plus a table whose data cells are marked GARBLED."""
    garbled = table(["Region", "Sales"], [["GARBLED", "GARBLED"], ["GARBLED", "GARBLED"]])
    return make_pdf(Page(blocks=(paragraph("A damaged table follows."), garbled)))


def pdf_prose() -> bytes:
    return make_pdf(text_page("Only prose here, with no table."))


# --- VC-123: unreadable parts pause before any model call (FR-119, FR-122) ------------------------


def test_image_only_pages_pause_before_any_model_call(make_settings, table_store_dir: Path) -> None:
    """VC-123: pages 2–3 image-only in a 4-page PDF → ask_unreadable before any model call."""
    # Given a table on page 1, image-only pages 2 and 3, and prose on page 4
    pdf = pdf_image_gap()
    with open_document(pdf) as doc:
        assert doc.page_count == 4
        assert pages_without_text(doc) == [2, 3]
    tables = readable_tables(pdf)
    settings = make_settings()
    graph, deps, scripted, index = open_run(settings, [enrichment_for(tables[0])])
    # When the run starts
    result = run_ingestion(graph, deps, SOURCE_FILE, pdf)
    # Then it pauses, naming those pages with an en dash, and the model was not called
    question = require_pause(result, deps)
    assert question["pause"] == "ask_unreadable"
    assert question["intro"] == UNREADABLE_INTRO
    assert question["bullets"] == [NO_TEXT_BULLET]
    assert question["question"] == UNREADABLE_QUESTION
    assert question["choices"] == [CANCEL_CHOICE, CONTINUE_CHOICE]
    assert scripted.calls == []
    assert index.calls == []
    assert index.ids(settings.PINECONE_NAMESPACE) == []
    assert files_in(table_store_dir) == []
    (part,) = result.values["skipped"]
    assert part["kind"] == "no_text_pages"
    assert part["pages"] == [2, 3]
    assert part["table_id"] == ""


def test_unreadable_table_is_named_and_never_sent_to_the_model(
    make_settings, table_store_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """VC-123: a table whose cells are mostly `�` → bullet "a table on page N"; the stub never receives `�`."""
    # Given a readable table on page 1 and a table on page 2 whose cells are mostly the replacement character
    patch_replacement_cells(monkeypatch)
    pdf = pdf_with_unreadable_table()
    found = all_tables(pdf)
    readable = [item for item in found if not item.unreadable]
    unreadable = [item for item in found if item.unreadable]
    assert [item.pages for item in readable] == [[1]]
    assert [item.pages for item in unreadable] == [[2]]
    settings = make_settings()
    graph, deps, scripted, index = open_run(settings, [enrichment_for(readable[0])])
    # When the run starts / Then it pauses on that table before any model call
    paused = run_ingestion(graph, deps, SOURCE_FILE, pdf)
    question = require_pause(paused, deps)
    assert question["pause"] == "ask_unreadable"
    assert question["bullets"] == ["a table on page 2"]
    assert scripted.calls == []
    # When the user continues / Then the readable Table is sent and indexed, and no message contains `�`
    finished = resume_ingestion(graph, deps, paused.thread_id, "continue")
    assert len(scripted.calls) == 1
    assert REPLACEMENT not in all_message_text(scripted)
    assert finished.status == "finished"
    assert finished.values["outcome"] == {"status": "indexed", "message": indexed_message(1)}
    assert index.ids(settings.PINECONE_NAMESPACE) == files_in(table_store_dir) == [readable[0].table_id]
    assert unreadable[0].table_id not in index.ids(settings.PINECONE_NAMESPACE)
    assert deps.runs.thread_ids() == []


# --- VC-124: continue indexes, cancel writes nothing (FR-120, BR-103) ------------------------------


def test_continue_indexes_the_readable_tables(make_settings, table_store_dir: Path) -> None:
    """VC-124: Continue at the unreadable-pages pause indexes the readable Tables."""
    # Given the 4-page PDF paused on pages 2–3
    pdf = pdf_image_gap()
    tables = readable_tables(pdf)
    settings = make_settings()
    graph, deps, scripted, index = open_run(settings, [enrichment_for(tables[0])])
    paused = run_ingestion(graph, deps, SOURCE_FILE, pdf)
    assert require_pause(paused, deps)["pause"] == "ask_unreadable"
    # When the user continues
    finished = resume_ingestion(graph, deps, paused.thread_id, "continue")
    # Then the readable Table is indexed: one record and its parquet file
    assert finished.status == "finished"
    assert finished.values["outcome"] == {"status": "indexed", "message": indexed_message(1)}
    assert [item["metadata"]["table_id"] for item in finished.values["assembled"]] == [tables[0].table_id]
    assert index.ids(settings.PINECONE_NAMESPACE) == files_in(table_store_dir) == [tables[0].table_id]
    assert "upsert" in index.calls
    assert deps.runs.thread_ids() == []


def test_cancel_at_the_unreadable_pause_leaves_the_previous_version(make_settings, table_store_dir: Path) -> None:
    """VC-124: Cancel at that pause writes and deletes nothing, and says the ingestion was cancelled."""
    # Given the same pause, and a previous report.pdf record already in the index
    pdf = pdf_image_gap()
    tables = readable_tables(pdf)
    settings = make_settings()
    graph, deps, scripted, index = open_run(settings, [enrichment_for(tables[0])])
    plant_previous(index, settings.PINECONE_NAMESPACE)
    paused = run_ingestion(graph, deps, SOURCE_FILE, pdf)
    assert require_pause(paused, deps)["pause"] == "ask_unreadable"
    assert scripted.calls == []
    assert index.calls == []
    # When the user cancels
    finished = resume_ingestion(graph, deps, paused.thread_id, "cancel")
    # Then nothing was written or deleted, and the chat says so
    assert finished.status == "finished"
    assert finished.values["outcome"] == {"status": "cancelled", "message": CANCELLED_MESSAGE}
    assert index.calls == []
    assert index.ids(settings.PINECONE_NAMESPACE) == [PREVIOUS_ID]
    assert index.records[settings.PINECONE_NAMESPACE][PREVIOUS_ID]["metadata"] == PREVIOUS_METADATA
    assert files_in(table_store_dir) == []
    assert deps.runs.thread_ids() == []


# --- VC-134, VC-135, VC-136: retries (FR-132, FR-133) -----------------------------------------------


def test_a_table_is_indexed_on_the_third_attempt(make_settings, table_store_dir: Path) -> None:
    """VC-134: INGESTION_MAX_RETRIES=2, invalid twice then valid → 3 calls; the third carries the retry sections."""
    # Given a retry limit of 2 and two invalid answers followed by a valid one
    pdf = pdf_one_table()
    tables = readable_tables(pdf)
    settings = make_settings(INGESTION_MAX_RETRIES="2")
    answers = [invalid_enrichment(tables[0]), invalid_enrichment(tables[0]), enrichment_for(tables[0])]
    graph, deps, scripted, index = open_run(settings, answers)
    # When the run goes through
    finished = run_ingestion(graph, deps, SOURCE_FILE, pdf)
    # Then the third human message received the previous answer and the feedback, and the Table is indexed
    assert len(scripted.calls) == 3
    third = human_text(scripted.calls[2])
    assert "Previous answer" in third
    assert "Feedback to fix" in third
    assert third.index("Previous answer") < third.index("Feedback to fix")
    assert "Feedback to fix" not in human_text(scripted.calls[0])
    assert finished.status == "finished"
    assert finished.values["outcome"] == {"status": "indexed", "message": indexed_message(1)}
    assert index.ids(settings.PINECONE_NAMESPACE) == files_in(table_store_dir) == [tables[0].table_id]
    assert deps.runs.thread_ids() == []


def test_three_invalid_answers_pause_as_skipped(make_settings, table_store_dir: Path) -> None:
    """VC-134: invalid 3 times → paused at ask_skipped after 3 calls."""
    # Given a retry limit of 2 and three invalid answers
    pdf = pdf_one_table()
    tables = readable_tables(pdf)
    settings = make_settings(INGESTION_MAX_RETRIES="2")
    answers = [invalid_enrichment(tables[0]), invalid_enrichment(tables[0]), invalid_enrichment(tables[0])]
    graph, deps, scripted, index = open_run(settings, answers)
    # When the run uses every attempt
    result = run_ingestion(graph, deps, SOURCE_FILE, pdf)
    # Then the Table is skipped and the run pauses after exactly 3 calls
    question = require_pause(result, deps)
    assert len(scripted.calls) == 3
    assert question["pause"] == "ask_skipped"
    assert result.values["assembled"] == []
    assert result.values["skipped"] == [
        {"kind": "table", "pages": [1], "table_id": tables[0].table_id, "caption": ""},
    ]
    assert index.calls == []
    assert files_in(table_store_dir) == []


def test_zero_retries_skips_a_table_after_one_attempt(make_settings, table_store_dir: Path) -> None:
    """VC-135: INGESTION_MAX_RETRIES=0, invalid once → the Table is skipped after 1 call."""
    # Given no retries and one invalid answer
    pdf = pdf_one_table()
    tables = readable_tables(pdf)
    settings = make_settings(INGESTION_MAX_RETRIES="0")
    graph, deps, scripted, index = open_run(settings, [invalid_enrichment(tables[0])])
    # When the run starts
    result = run_ingestion(graph, deps, SOURCE_FILE, pdf)
    # Then a single call is enough to skip the Table
    question = require_pause(result, deps)
    assert len(scripted.calls) == 1
    assert "Feedback to fix" not in human_text(scripted.calls[0])
    assert question["pause"] == "ask_skipped"
    assert result.values["skipped"] == [
        {"kind": "table", "pages": [1], "table_id": tables[0].table_id, "caption": ""},
    ]
    assert result.values["assembled"] == []
    assert index.calls == []
    assert files_in(table_store_dir) == []


def test_the_next_table_does_not_inherit_feedback(make_settings, table_store_dir: Path) -> None:
    """VC-136: two Tables, the first needing one retry → the second Table's first message has no feedback."""
    # Given two Tables and a retry limit that allows the first Table one more attempt
    pdf = pdf_two_tables()
    tables = readable_tables(pdf)
    assert [item.columns for item in tables] == [["Region", "Sales"], ["Product", "Units"]]
    settings = make_settings()
    answers = [invalid_enrichment(tables[0]), enrichment_for(tables[0]), enrichment_for(tables[1])]
    graph, deps, scripted, index = open_run(settings, answers)
    # When both Tables are enriched
    finished = run_ingestion(graph, deps, SOURCE_FILE, pdf)
    # Then the first Table's retry carries feedback, and the second Table's first message does not
    assert len(scripted.calls) == 3
    assert "Region" in human_text(scripted.calls[0])
    assert "Feedback to fix" not in human_text(scripted.calls[0])
    assert "Feedback to fix" in human_text(scripted.calls[1])
    second_first = human_text(scripted.calls[2])
    assert "Product" in second_first
    assert "Feedback to fix" not in second_first
    assert "Previous answer" not in second_first
    assert finished.status == "finished"
    assert finished.values["outcome"] == {"status": "indexed", "message": indexed_message(2)}
    assert index.ids(settings.PINECONE_NAMESPACE) == files_in(table_store_dir) == sorted(
        item.table_id for item in tables
    )
    assert deps.runs.thread_ids() == []


# --- VC-137: ask_skipped (FR-134, FR-135) -----------------------------------------------------------


def test_one_skipped_table_can_be_indexed(make_settings, table_store_dir: Path) -> None:
    """VC-137: 3 Tables, 1 skipped → the pause names its pages and caption; Index 2 stores the other two."""
    # Given three Tables and a retry limit of 0, so one invalid answer skips the captioned Table
    pdf = pdf_three_tables()
    tables = readable_tables(pdf)
    settings = make_settings(INGESTION_MAX_RETRIES="0")
    answers = [enrichment_for(tables[0]), invalid_enrichment(tables[1]), enrichment_for(tables[2])]
    graph, deps, scripted, index = open_run(settings, answers)
    # When every Table has been through validate
    paused = run_ingestion(graph, deps, SOURCE_FILE, pdf)
    # Then the pause offers the other two Tables and names the skipped one's page and caption
    question = require_pause(paused, deps)
    assert len(scripted.calls) == 3
    assert question["pause"] == "ask_skipped"
    assert question["intro"] == SKIPPED_INTRO
    assert question["bullets"] == ["page 2: Table 2. Regional sales"]
    assert question["question"] == "Index the other 2 tables, or cancel?"
    assert question["choices"] == [CANCEL_CHOICE, {"value": "index", "label": "Index 2"}]
    assert paused.values["skipped"] == [
        {"kind": "table", "pages": [2], "table_id": tables[1].table_id, "caption": "Table 2. Regional sales"},
    ]
    kept = sorted([tables[0].table_id, tables[2].table_id])
    assert sorted(item["metadata"]["table_id"] for item in paused.values["assembled"]) == kept
    # When the user indexes the rest
    finished = resume_ingestion(graph, deps, paused.thread_id, "index")
    # Then exactly those two Tables are stored
    assert finished.status == "finished"
    assert finished.values["outcome"] == {"status": "indexed", "message": indexed_message(2)}
    assert index.ids(settings.PINECONE_NAMESPACE) == files_in(table_store_dir) == kept
    assert tables[1].table_id not in index.ids(settings.PINECONE_NAMESPACE)
    assert deps.runs.thread_ids() == []


def test_cancel_at_the_skipped_pause_writes_nothing(make_settings, table_store_dir: Path) -> None:
    """VC-137: Cancel at ask_skipped writes and deletes nothing."""
    # Given the same pause, and a previous report.pdf record
    pdf = pdf_three_tables()
    tables = readable_tables(pdf)
    settings = make_settings(INGESTION_MAX_RETRIES="0")
    answers = [enrichment_for(tables[0]), invalid_enrichment(tables[1]), enrichment_for(tables[2])]
    graph, deps, scripted, index = open_run(settings, answers)
    plant_previous(index, settings.PINECONE_NAMESPACE)
    paused = run_ingestion(graph, deps, SOURCE_FILE, pdf)
    assert require_pause(paused, deps)["question"] == "Index the other 2 tables, or cancel?"
    assert index.calls == []
    assert files_in(table_store_dir) == []
    # When the user cancels
    finished = resume_ingestion(graph, deps, paused.thread_id, "cancel")
    # Then the previous record is untouched and no file was written
    assert finished.status == "finished"
    assert finished.values["outcome"] == {"status": "cancelled", "message": CANCELLED_MESSAGE}
    assert index.calls == []
    assert index.ids(settings.PINECONE_NAMESPACE) == [PREVIOUS_ID]
    assert index.records[settings.PINECONE_NAMESPACE][PREVIOUS_ID]["metadata"] == PREVIOUS_METADATA
    assert files_in(table_store_dir) == []
    assert deps.runs.thread_ids() == []


def test_every_table_skipped_offers_only_cancel(make_settings, table_store_dir: Path) -> None:
    """VC-137: all 3 Tables skipped → "No table could be processed. Cancel?" and only the cancel choice."""
    # Given three Tables and a retry limit of 0, every answer invalid
    pdf = pdf_three_tables()
    tables = readable_tables(pdf)
    settings = make_settings(INGESTION_MAX_RETRIES="0")
    graph, deps, scripted, index = open_run(settings, [invalid_enrichment(item) for item in tables])
    # When every Table is skipped
    result = run_ingestion(graph, deps, SOURCE_FILE, pdf)
    # Then the only choice is cancel, and each skipped Table is listed
    question = require_pause(result, deps)
    assert len(scripted.calls) == 3
    assert question["pause"] == "ask_skipped"
    assert question["intro"] == SKIPPED_INTRO
    assert question["question"] == "No table could be processed. Cancel?"
    assert question["choices"] == [CANCEL_CHOICE]
    assert question["bullets"] == [
        "page 1",
        "page 2: Table 2. Regional sales",
        "page 3",
    ]
    assert result.values["assembled"] == []
    assert [(part["pages"], part["caption"]) for part in result.values["skipped"]] == [
        ([1], ""),
        ([2], "Table 2. Regional sales"),
        ([3], ""),
    ]
    assert index.calls == []
    assert files_in(table_store_dir) == []


# --- VC-145: nothing to index (FR-142) --------------------------------------------------------------


def test_text_without_tables_keeps_the_previous_version(make_settings, table_store_dir: Path) -> None:
    """VC-145: a PDF with text and no tables → the no-tables sentence; nothing written; previous record intact."""
    # Given prose with no table, and a previous report.pdf record
    pdf = pdf_prose()
    assert readable_tables(pdf) == []
    settings = make_settings()
    graph, deps, scripted, index = open_run(settings, [])
    plant_previous(index, settings.PINECONE_NAMESPACE)
    # When the run starts
    result = run_ingestion(graph, deps, SOURCE_FILE, pdf)
    # Then it finishes without calling the model or the index
    assert result.status == "finished"
    assert result.values["outcome"] == {"status": "no_tables", "message": NO_TABLES_MESSAGE}
    assert scripted.calls == []
    assert index.calls == []
    assert index.ids(settings.PINECONE_NAMESPACE) == [PREVIOUS_ID]
    assert index.records[settings.PINECONE_NAMESPACE][PREVIOUS_ID]["metadata"] == PREVIOUS_METADATA
    assert files_in(table_store_dir) == []
    assert deps.runs.thread_ids() == []


def test_continuing_past_an_unreadable_only_pdf_indexes_nothing(
    make_settings, table_store_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """VC-145: a PDF whose only table is unreadable, then Continue → the nothing-indexed sentence."""
    # Given a single unreadable table and a previous report.pdf record
    patch_replacement_cells(monkeypatch)
    pdf = pdf_only_unreadable()
    found = all_tables(pdf)
    assert len(found) == 1 and found[0].unreadable and found[0].pages == [1]
    settings = make_settings()
    graph, deps, scripted, index = open_run(settings, [])
    plant_previous(index, settings.PINECONE_NAMESPACE)
    paused = run_ingestion(graph, deps, SOURCE_FILE, pdf)
    assert require_pause(paused, deps)["pause"] == "ask_unreadable"
    # When the user continues
    finished = resume_ingestion(graph, deps, paused.thread_id, "continue")
    # Then nothing is indexed and the model is not called
    assert finished.status == "finished"
    assert finished.values["outcome"] == {"status": "nothing_indexed", "message": NOTHING_INDEXED_MESSAGE}
    assert scripted.calls == []
    assert index.calls == []
    assert index.ids(settings.PINECONE_NAMESPACE) == [PREVIOUS_ID]
    assert index.records[settings.PINECONE_NAMESPACE][PREVIOUS_ID]["metadata"] == PREVIOUS_METADATA
    assert files_in(table_store_dir) == []
    assert deps.runs.thread_ids() == []


# --- VC-147: same bytes, same ids (BR-104) ----------------------------------------------------------


def test_the_same_bytes_twice_keep_the_same_record_ids(make_settings, table_store_dir: Path) -> None:
    """VC-147: the same bytes ingested twice through the graph → the same ids and the same record count."""
    # Given one PDF and one deps object shared by both runs
    pdf = pdf_one_table()
    tables = readable_tables(pdf)
    settings = make_settings()
    answer = enrichment_for(tables[0])
    graph, deps, scripted, index = open_run(settings, [answer, answer])
    # When the same bytes are ingested twice
    first = run_ingestion(graph, deps, SOURCE_FILE, pdf)
    assert first.status == "finished"
    assert deps.runs.thread_ids() == []
    first_ids = index.ids(settings.PINECONE_NAMESPACE)
    second = run_ingestion(graph, deps, SOURCE_FILE, pdf)
    # Then the ids and the count are unchanged
    assert second.status == "finished"
    assert index.ids(settings.PINECONE_NAMESPACE) == first_ids == [tables[0].table_id]
    assert len(index.ids(settings.PINECONE_NAMESPACE)) == len(first_ids)
    assert files_in(table_store_dir) == first_ids
    assert deps.runs.thread_ids() == []


# --- VC-159: secrets stay out of prompts and state (BR-107) -----------------------------------------


def test_fake_secrets_stay_out_of_prompts_and_state(make_settings, table_store_dir: Path) -> None:
    """VC-159: Settings built from the fake secrets → none of them in the stub's messages or the graph state."""
    # Given the default fake secrets (make_settings uses FAKE_LITELLM_KEY, FAKE_PINECONE_KEY, FAKE_LANGSMITH_KEY)
    pdf = pdf_one_table()
    tables = readable_tables(pdf)
    settings = make_settings()
    assert settings.LITELLM_API_KEY is not None
    assert settings.LITELLM_API_KEY.get_secret_value() == FAKE_LITELLM_KEY
    graph, deps, scripted, index = open_run(settings, [enrichment_for(tables[0])])
    # When a Table is indexed
    result = run_ingestion(graph, deps, SOURCE_FILE, pdf)
    # Then no secret value appears in any recorded message or in the state
    assert result.status == "finished"
    assert len(scripted.calls) == 1
    recorded = all_message_text(scripted)
    state = str(result.values)
    for secret in SECRETS:
        assert secret not in recorded
        assert secret not in state
    assert deps.runs.thread_ids() == []
