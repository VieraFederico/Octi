"""The ingestion graph's nodes, each called on its own (spec 01 §7 "Ingestion graph")."""

import logging

import pandas as pd
import pymupdf
import pytest

from agents.ingestion import nodes
from agents.ingestion.indexing import assemble_metadata, exceeds_size_guard, index_metadata
from agents.ingestion.pdf.cleaning import dtype_name, rows_as_text
from agents.ingestion.pdf.context import collect_context
from agents.ingestion.prompts import ROWS_TO_LLM
from agents.ingestion.schemas import ColumnDescription, TableEnrichment
from agents.ingestion.state import IngestionDeps
from services.errors import ProxyUnreachableError
from tests.pdf_fixtures import Page, encrypt, image_covering, image_only_page, make_pdf, paragraph, table, text_page
from tests.stubs import (
    FakeEmbeddings,
    FakePineconeIndex,
    ScriptedChatModel,
    enrichment_for,
    extracted_table,
    invalid_enrichment,
    openai_connection_error,
)

THREAD = "thread-1"
FILE = "report.pdf"
SHA = "a" * 64
CONTEXT = {
    "section": "Results",
    "caption": "Table 2. Sales by region",
    "before": "The following figures are unaudited.",
    "after": "",
    "footnotes": "(1) Excludes taxes.",
}
MONTH_HEADER = ["Month", "Units", "Returns"]


def make_deps(make_settings, *, scripted=None, embeddings=None, index=None, **settings_overrides):
    """Deps whose chat model, embeddings and index are the stubs a test passed."""
    scripted = ScriptedChatModel([]) if scripted is None else scripted
    deps = IngestionDeps(
        settings=make_settings(**settings_overrides),
        embeddings=FakeEmbeddings() if embeddings is None else embeddings,
        index=FakePineconeIndex() if index is None else index,
        make_chat_model=scripted.build,
    )
    return deps, scripted


def open_run(deps: IngestionDeps, pdf: bytes, **extra) -> dict:
    """The run input, with the PDF kept in the per-run store."""
    deps.runs.open(THREAD, pdf)
    state = {
        "thread_id": THREAD,
        "source_file": FILE,
        "max_retries": 2,
        "assembled": [],
        "skipped": [],
    }
    state.update(extra)
    return state


def sales_table(**kwargs):
    return extracted_table(["Region", "Sales"], [["North", "10"], ["South", "12"]], **kwargs)


def table_view(extracted, context=None) -> dict:
    """A `TableState` for `extracted`, the way `extract_tables` would leave it."""
    frame = extracted.frame
    return {
        "table_id": extracted.table_id,
        "pages": list(extracted.pages),
        "columns": list(extracted.columns),
        "dtypes": [dtype_name(frame[name]) for name in extracted.columns],
        "hints": {name: list(hints) for name, hints in extracted.hints.items()},
        "row_headers": list(extracted.row_headers),
        "rows": rows_as_text(frame, ROWS_TO_LLM),
        "n_rows": len(frame),
        "context": context,
    }


def place_table(deps: IngestionDeps, extracted, *, context=None, **extra) -> dict:
    """Open a run that already holds `extracted`, as `load_pdf` / `extract_tables` would have left it."""
    state = open_run(
        deps, b"%PDF-1.4", document_sha=SHA, current=0, attempts=0, feedback=[], answer=None
    )
    deps.runs.get(THREAD).tables[extracted.table_id] = extracted
    chosen = CONTEXT if context is None else context
    state["tables"] = [table_view(extracted, chosen)]
    state.update(extra)
    return state


def assembled_item(extracted, source_file: str = FILE) -> dict:
    """One assembled item, built the way `validate` builds it."""
    enrichment = enrichment_for(extracted)
    metadata = assemble_metadata(enrichment, extracted, source_file)
    return {
        "metadata": metadata.model_dump(mode="json"),
        "record_metadata": index_metadata(metadata, extracted, SHA),
    }


def pause_at(monkeypatch: pytest.MonkeyPatch, resume: str) -> dict:
    """Replace `interrupt` so a pause returns `resume` and the question is kept for the test."""
    seen: dict = {}

    def fake(question):
        seen["question"] = question
        return resume

    monkeypatch.setattr(nodes, "interrupt", fake)
    return seen


def has_payload(value: object) -> bool:
    """True when `value` holds PDF bytes or a DataFrame anywhere inside it."""
    if isinstance(value, (bytes, bytearray, pd.DataFrame)):
        return True
    if isinstance(value, dict):
        return any(has_payload(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(has_payload(item) for item in value)
    return False


def assert_nothing_touched(scripted: ScriptedChatModel, deps: IngestionDeps, table_store_dir) -> None:
    """No model call and nothing written (FR-108)."""
    assert scripted.calls == [] and scripted.model_names == []
    assert deps.embeddings.calls == []
    assert deps.index.calls == []
    assert list(table_store_dir.glob("*")) == []


def refuse_write(monkeypatch: pytest.MonkeyPatch) -> None:
    """`index` must not call `write_document` when there is nothing to store."""

    def forbidden(*_args, **_kwargs):
        raise AssertionError("write_document must not be called")

    monkeypatch.setattr(nodes, "write_document", forbidden)


def month_rows(first: int, last: int) -> list[list[str]]:
    return [[f"M{n:02d}", str(n), str(n * 2)] for n in range(first, last + 1)]


def skipped_table(pages: list[int], caption: str, table_id: str = "t") -> dict:
    return {"kind": "table", "pages": pages, "table_id": table_id, "caption": caption}


# --- format_pages -------------------------------------------------------------------------------


def test_format_pages_names_one_page_a_range_or_a_list() -> None:
    """S01-D-021: one page, a consecutive run (en dash) and any other list."""
    # Given page lists a pause might name
    # When they are formatted / Then each takes the form the pauses show
    assert nodes.format_pages([3]) == "page 3"
    assert nodes.format_pages([4, 5]) == "pages 4\u20135"
    assert nodes.format_pages([12, 13, 14]) == "pages 12\u201314"
    assert nodes.format_pages([2, 5]) == "pages 2, 5"
    assert nodes.format_pages([2, 3, 5]) == "pages 2, 3, 5"


# --- load_pdf -----------------------------------------------------------------------------------


def test_load_pdf_rejects_bytes_that_are_not_a_pdf(make_settings, table_store_dir) -> None:
    """VC-105 (FR-105, FR-108): bytes that are not a PDF end the run before any call or write."""
    # Given bytes that are not a PDF, and stubs that would record any call
    deps, scripted = make_deps(make_settings)
    state = open_run(deps, b"not a pdf")
    # When the PDF is loaded
    result = nodes.load_pdf(state, deps)
    # Then the run failed with the FR-105 sentence and nothing was touched
    assert result == {
        "outcome": {
            "status": "failed",
            "message": "I couldn't open this file. It may be damaged or not a real PDF.",
        }
    }
    assert deps.runs.get(THREAD).document is None
    assert_nothing_touched(scripted, deps, table_store_dir)


def test_load_pdf_rejects_a_password_protected_pdf(make_settings, table_store_dir) -> None:
    """VC-106 (FR-106, FR-108): an encrypted PDF ends the run before any call or write."""
    # Given a password-protected PDF
    deps, scripted = make_deps(make_settings)
    state = open_run(deps, encrypt(make_pdf(text_page("Hello"))))
    # When the PDF is loaded
    result = nodes.load_pdf(state, deps)
    # Then the run failed with the FR-106 sentence and nothing was touched
    assert result == {
        "outcome": {
            "status": "failed",
            "message": "This PDF is password-protected. Remove the password and upload it again.",
        }
    }
    assert deps.runs.get(THREAD).document is None
    assert_nothing_touched(scripted, deps, table_store_dir)


def test_load_pdf_rejects_a_pdf_with_no_selectable_text(make_settings, table_store_dir) -> None:
    """VC-107 (FR-107, FR-108): a PDF of only images ends the run before any call or write."""
    # Given a PDF whose only page is an image
    deps, scripted = make_deps(make_settings)
    state = open_run(deps, make_pdf(image_only_page()))
    # When the PDF is loaded
    result = nodes.load_pdf(state, deps)
    # Then the run failed with the FR-107 sentence and nothing was touched
    assert result == {
        "outcome": {
            "status": "failed",
            "message": "This PDF has no selectable text (it looks scanned). I can only read PDFs with selectable text.",
        }
    }
    assert deps.runs.get(THREAD).document is None
    assert_nothing_touched(scripted, deps, table_store_dir)


def test_load_pdf_groups_pages_without_text_and_names_image_pages(make_settings) -> None:
    """FR-119, FR-121: consecutive pages without text are one skipped part; a large image is listed."""
    # Given a text page with an image, two scanned pages, a text page and one more scanned page
    pdf = make_pdf(
        text_page("Introduction.", image_covering(0.05, shade=10)),
        image_only_page(shade=20),
        image_only_page(shade=21),
        text_page("More text."),
        image_only_page(shade=22),
    )
    deps, _scripted = make_deps(make_settings)
    state = open_run(deps, pdf)
    try:
        # When the PDF is loaded
        result = nodes.load_pdf(state, deps)
        # Then the hash, the page count, the image page and one part per run are returned
        assert "outcome" not in result
        assert result["page_count"] == 5
        assert result["image_pages"] == [1]
        assert len(result["document_sha"]) == 64
        assert result["skipped"] == [
            {"kind": "no_text_pages", "pages": [2, 3], "table_id": "", "caption": ""},
            {"kind": "no_text_pages", "pages": [5], "table_id": "", "caption": ""},
        ]
        assert deps.runs.get(THREAD).document is not None
    finally:
        # Clean
        deps.runs.close(THREAD)


# --- extract_tables -----------------------------------------------------------------------------


def test_extract_tables_stores_readable_tables_and_skips_unreadable_ones(make_settings, monkeypatch) -> None:
    """FR-119: a readable table goes into the state and the store; an unreadable one is only a skipped part."""
    real_extract = pymupdf.table.Table.extract

    def garbled_extract(self: pymupdf.table.Table):
        rows = real_extract(self)
        return [[cell.replace("GARBLED", "\ufffd\ufffd") if cell else cell for cell in row] for row in rows]

    monkeypatch.setattr(pymupdf.table.Table, "extract", garbled_extract)
    # Given a PDF with one readable table and one whose cells are mostly unreadable
    pdf = make_pdf(
        Page(
            blocks=(
                table(["Region", "Sales"], [["North", "10"], ["South", "12"]]),
                paragraph("An unreadable table follows."),
                table(["Region", "Sales"], [["GARBLED", "GARBLED"], ["GARBLED", "GARBLED"]]),
            )
        )
    )
    deps, _scripted = make_deps(make_settings)
    state = open_run(deps, pdf)
    try:
        loaded = nodes.load_pdf(state, deps)
        # When the tables are extracted
        result = nodes.extract_tables({**state, **loaded}, deps)
        # Then only the readable table is in the state and the store
        assert result["current"] == 0 and result["attempts"] == 0
        assert result["feedback"] == [] and result["answer"] is None
        (readable,) = result["tables"]
        assert readable["context"] is None
        assert readable["n_rows"] == 2 and len(readable["rows"]) <= ROWS_TO_LLM
        assert not has_payload(result)
        stored = deps.runs.get(THREAD).tables
        assert list(stored) == [readable["table_id"]]
        assert isinstance(stored[readable["table_id"]].frame, pd.DataFrame)
        (skipped,) = result["skipped"]
        assert skipped["kind"] == "unreadable_table"
        assert skipped["pages"] == [1] and skipped["caption"] == ""
        assert skipped["table_id"].endswith("-p1-t2")
        assert skipped["table_id"] not in stored
    finally:
        deps.runs.close(THREAD)


def test_a_two_hundred_row_table_stays_out_of_the_node_output(make_settings) -> None:
    """VC-167 (BR-111): a 200-row table leaves no bytes or DataFrame in a node output, and at most 20 rows."""
    # Given a 200-row table split over ten pages, the header repeated on each
    pages = [
        Page(blocks=(table(MONTH_HEADER, month_rows(start, start + 19)),)) for start in range(1, 201, 20)
    ]
    deps, _scripted = make_deps(make_settings)
    state = open_run(deps, make_pdf(*pages))
    try:
        # When the PDF is loaded, the tables extracted and their context collected
        loaded = nodes.load_pdf(state, deps)
        extracted = nodes.extract_tables({**state, **loaded}, deps)
        collected = nodes.collect_context({**state, **loaded, **extracted}, deps)
        # Then no output carries the bytes or the frame, and the state shows at most 20 rows
        for output in (loaded, extracted, collected):
            assert not has_payload(output)
        (view,) = extracted["tables"]
        assert view["n_rows"] == 200
        assert len(view["rows"]) <= 20
        assert len(collected["tables"][0]["rows"]) <= 20
        frame = deps.runs.get(THREAD).tables[view["table_id"]].frame
        assert isinstance(frame, pd.DataFrame) and len(frame) == 200
        assert isinstance(deps.runs.get(THREAD).pdf, bytes)
    finally:
        deps.runs.close(THREAD)


# --- ask_unreadable -----------------------------------------------------------------------------


def test_ask_unreadable_pauses_with_the_parts_in_page_order(make_settings, monkeypatch) -> None:
    """FR-119: the pause names every unreadable part in page order and offers Cancel and Continue."""
    # Given skipped parts stored out of page order
    deps, _scripted = make_deps(make_settings)
    state = open_run(
        deps,
        b"%PDF-1.4",
        skipped=[
            {"kind": "no_text_pages", "pages": [12, 13, 14], "table_id": "", "caption": ""},
            {"kind": "unreadable_table", "pages": [7], "table_id": "tid", "caption": "ignored"},
            {"kind": "no_text_pages", "pages": [2, 3], "table_id": "", "caption": ""},
        ],
    )
    seen = pause_at(monkeypatch, "continue")
    # When the run pauses and the user continues
    result = nodes.ask_unreadable(state, deps)
    # Then the question is the FR-119 text and the run goes on
    assert seen["question"] == {
        "pause": "ask_unreadable",
        "intro": "I couldn't read some parts of report.pdf:",
        "bullets": [
            "pages 2\u20133 (no selectable text)",
            "a table on page 7",
            "pages 12\u201314 (no selectable text)",
        ],
        "question": "They won't be indexed. Continue with the rest, or cancel?",
        "choices": [
            {"value": "cancel", "label": "Cancel ingestion"},
            {"value": "continue", "label": "Continue"},
        ],
    }
    assert result == {}


def test_ask_unreadable_cancel_ends_the_run(make_settings, monkeypatch) -> None:
    """FR-120: Cancel ingestion ends the run and says nothing was indexed."""
    # Given the unreadable-parts pause
    deps, scripted = make_deps(make_settings)
    state = open_run(
        deps,
        b"%PDF-1.4",
        skipped=[{"kind": "no_text_pages", "pages": [2], "table_id": "", "caption": ""}],
    )
    pause_at(monkeypatch, "cancel")
    # When the user cancels
    result = nodes.ask_unreadable(state, deps)
    # Then the run is cancelled and no model was called
    assert result == {
        "outcome": {
            "status": "cancelled",
            "message": "Ingestion cancelled. Nothing from report.pdf was indexed.",
        }
    }
    assert scripted.calls == [] and deps.embeddings.calls == [] and deps.index.calls == []


def test_ask_unreadable_rejects_any_other_answer(make_settings, monkeypatch) -> None:
    """FR-119: a resume value other than continue or cancel is refused."""
    deps, _scripted = make_deps(make_settings)
    state = open_run(
        deps,
        b"%PDF-1.4",
        skipped=[{"kind": "unreadable_table", "pages": [4], "table_id": "tid", "caption": ""}],
    )
    pause_at(monkeypatch, "index")
    # When the pause is resumed with a value this question does not offer
    # Then the node refuses it
    with pytest.raises(ValueError):
        nodes.ask_unreadable(state, deps)


# --- collect_context ----------------------------------------------------------------------------


def test_collect_context_copies_the_five_fields_onto_every_table(make_settings) -> None:
    """FR-123: each table's context is the five fields collected for it."""
    # Given a PDF whose table has a heading and a caption
    pdf = make_pdf(
        Page(
            blocks=(
                "<h2>Regional results</h2>",
                "<p>Table 2. Sales by region</p>",
                table(["Region", "Sales"], [["North", "10"]]),
            )
        )
    )
    deps, _scripted = make_deps(make_settings)
    state = open_run(deps, pdf)
    try:
        loaded = nodes.load_pdf(state, deps)
        extracted = nodes.extract_tables({**state, **loaded}, deps)
        running = {**state, **loaded, **extracted}
        # When the context is collected
        result = nodes.collect_context(running, deps)
        # Then the state tables are the same tables with the five context fields filled
        document = deps.runs.get(THREAD).document
        stored = deps.runs.get(THREAD).tables
        assert list(result) == ["tables"]
        assert len(extracted["tables"]) == 1
        assert len(result["tables"]) == 1
        for before, after in zip(extracted["tables"], result["tables"], strict=True):
            expected = collect_context(document, stored[before["table_id"]])
            assert after["context"] == {
                "section": expected.section,
                "caption": expected.caption,
                "before": expected.before,
                "after": expected.after,
                "footnotes": expected.footnotes,
            }
            assert {**after, "context": None} == before
    finally:
        deps.runs.close(THREAD)


# --- enrich -------------------------------------------------------------------------------------


def test_enrich_calls_the_configured_model_with_structured_output(make_settings) -> None:
    """VC-130 (FR-127): enrich uses LLM_MODEL, even when the picker lists another model."""
    # Given a table and a scripted model, while the picker also offers another model
    extracted = sales_table()
    enrichment = enrichment_for(extracted)
    scripted = ScriptedChatModel([enrichment])
    deps, scripted = make_deps(make_settings, scripted=scripted, LLM_MODEL_CHOICES="another-model")
    state = place_table(deps, extracted)
    # When the table is enriched
    result = nodes.enrich(state, deps)
    # Then the recorded model is LLM_MODEL and the answer is the parsed object
    assert "another-model" in deps.settings.chat_model_choices
    assert scripted.model_names == [deps.settings.LLM_MODEL]
    assert scripted.structured == [(TableEnrichment, True)]
    assert result == {"attempts": 1, "answer": enrichment.model_dump()}


def test_a_retry_sends_the_previous_answer_and_the_feedback(make_settings) -> None:
    """FR-132: the second attempt's human message carries the previous answer and the feedback."""
    # Given a first attempt that failed the placeholder-name check
    extracted = sales_table()
    scripted = ScriptedChatModel([invalid_enrichment(extracted), enrichment_for(extracted)])
    deps, scripted = make_deps(make_settings, scripted=scripted)
    state = place_table(deps, extracted)
    first = nodes.enrich(state, deps)
    checked = nodes.validate({**state, **first}, deps)
    assert checked["feedback"] and "skipped" not in checked
    # When the same table is enriched again with that answer and feedback
    result = nodes.enrich({**state, **first, **checked}, deps)
    # Then the second human message shows both retry sections and the attempt count moved on
    human = scripted.calls[1][-1].content
    assert "Previous answer" in human
    assert "Feedback to fix" in human
    assert checked["feedback"][0] in human
    assert "Previous answer" not in scripted.calls[0][-1].content
    assert result["attempts"] == 2


def test_enrich_keeps_a_raw_dict_when_the_answer_does_not_parse(make_settings) -> None:
    """S01-D-015: an answer that is not a TableEnrichment is kept as the raw dict."""
    # Given a model that returns a JSON object the schema rejects
    deps, _scripted = make_deps(make_settings, scripted=ScriptedChatModel([{"name": "x"}]))
    state = place_table(deps, sales_table())
    # When the table is enriched
    result = nodes.enrich(state, deps)
    # Then the answer is that dict, not an empty object
    assert result["answer"] == {"name": "x"}
    assert result["attempts"] == 1
    assert "outcome" not in result


@pytest.mark.parametrize("error", [ProxyUnreachableError("x"), openai_connection_error()], ids=["leaf", "connection"])
def test_enrich_ends_the_run_when_the_model_call_fails(make_settings, table_store_dir, error) -> None:
    """VC-168 (FR-160, BR-106): a model failure ends the run with the FR-160 sentence and no skipped part."""
    # Given a model call that fails
    deps, _scripted = make_deps(make_settings, scripted=ScriptedChatModel([error]))
    state = place_table(deps, sales_table())
    # When the table is enriched
    result = nodes.enrich(state, deps)
    # Then the run failed with the fixed sentence, and the table is not a skipped part
    assert result == {
        "outcome": {
            "status": "failed",
            "message": (
                "Something went wrong on my side and I couldn't index report.pdf. "
                "Your previous version is unchanged."
            ),
        }
    }
    assert "skipped" not in result
    for banned in ("LiteLLM", "proxy", "Pinecone"):
        assert banned not in result["outcome"]["message"]
    assert deps.embeddings.calls == [] and deps.index.calls == []
    assert list(table_store_dir.glob("*")) == []


# --- validate -----------------------------------------------------------------------------------


def test_validate_assembles_a_valid_answer(make_settings) -> None:
    """FR-133, FR-136: a valid answer becomes one assembled item and produces no feedback."""
    # Given an answer that passes every check
    extracted = sales_table(pages=(3, 4))
    enrichment = enrichment_for(extracted)
    deps, _scripted = make_deps(make_settings)
    state = place_table(deps, extracted, attempts=1, answer=enrichment.model_dump())
    # When it is validated
    result = nodes.validate(state, deps)
    # Then it is assembled and nothing is skipped
    assert result["feedback"] == []
    assert "skipped" not in result
    (item,) = result["assembled"]
    assert item["metadata"]["table_id"] == extracted.table_id
    assert item["metadata"]["pages"] == [3, 4]
    assert item["metadata"]["source_file"] == FILE
    assert item["record_metadata"]["table_id"] == extracted.table_id
    assert not exceeds_size_guard(item["record_metadata"])


def test_validate_skips_metadata_over_the_size_guard(make_settings) -> None:
    """VC-144 (FR-141): 400 long column descriptions become a skipped table, not an assembled item."""
    # Given a valid answer whose Index metadata is over 38 KB
    names = [f"C{i}" for i in range(400)]
    extracted = extracted_table(names, [["x"] * 400])
    enrichment = TableEnrichment(
        name="Measurements by category and year",
        description="A wide table of measurements.",
        columns=[ColumnDescription(name=name, description="d" * 200, unit="not stated") for name in names],
    )
    metadata = assemble_metadata(enrichment, extracted, FILE)
    assert exceeds_size_guard(index_metadata(metadata, extracted, SHA))
    deps, _scripted = make_deps(make_settings)
    state = place_table(
        deps,
        extracted,
        context={**CONTEXT, "caption": "Wide caption"},
        attempts=1,
        answer=enrichment.model_dump(),
    )
    # When it is validated
    result = nodes.validate(state, deps)
    # Then the table is skipped for its size and nothing is assembled
    assert result["feedback"] == []
    assert "assembled" not in result
    assert result["skipped"] == [
        {"kind": "table", "pages": [1], "table_id": extracted.table_id, "caption": "Wide caption"}
    ]
    assert "d" * 200 not in str(result["skipped"])


def test_validate_returns_feedback_while_retries_remain(make_settings) -> None:
    """FR-132: feedback on an attempt still within the limit does not skip the table."""
    # Given a placeholder name on the attempt equal to the retry limit
    extracted = sales_table()
    deps, _scripted = make_deps(make_settings)
    state = place_table(deps, extracted, attempts=2, max_retries=2, answer=invalid_enrichment(extracted).model_dump())
    # When it is validated
    result = nodes.validate(state, deps)
    # Then the feedback is returned and the table is not skipped yet
    assert result["feedback"]
    assert "skipped" not in result and "assembled" not in result


def test_skipped_table_feedback_is_logged_and_kept_out_of_the_part(make_settings, caplog) -> None:
    """VC-160 (BR-106): a skipped table's feedback is in the DEBUG log only, never in the skipped part."""
    # Given feedback on the attempt past the retry limit
    caplog.set_level(logging.DEBUG, logger="agents.ingestion.nodes")
    extracted = sales_table()
    deps, _scripted = make_deps(make_settings)
    state = place_table(
        deps,
        extracted,
        context={**CONTEXT, "caption": "Regional sales"},
        attempts=3,
        max_retries=2,
        answer=invalid_enrichment(extracted).model_dump(),
    )
    # When it is validated
    result = nodes.validate(state, deps)
    # Then the table is skipped, the feedback stays out of that part, and the log has it
    (sentence,) = result["feedback"]
    assert "outcome" not in result
    assert result["skipped"] == [
        {"kind": "table", "pages": [1], "table_id": extracted.table_id, "caption": "Regional sales"}
    ]
    assert sentence not in str(result["skipped"])
    assert sentence in caplog.text


# --- next_table ---------------------------------------------------------------------------------


def test_next_table_advances_and_clears_the_attempt(make_settings) -> None:
    """FR-133: the next table starts at attempt zero with no feedback and no answer."""
    deps, _scripted = make_deps(make_settings)
    state = {"current": 1, "attempts": 3, "feedback": ["The name is a placeholder."], "answer": {"name": "Table 1"}}
    # When the run moves on
    result = nodes.next_table(state, deps)
    # Then the counters are reset
    assert result == {"current": 2, "attempts": 0, "feedback": [], "answer": None}


# --- ask_skipped --------------------------------------------------------------------------------


def test_ask_skipped_offers_the_other_tables(make_settings, monkeypatch) -> None:
    """FR-134: with tables left, the pause names each skipped table and offers Index N."""
    # Given two skipped tables and two that were assembled; other skipped kinds are not bullets
    deps, _scripted = make_deps(make_settings)
    state = open_run(
        deps,
        b"%PDF-1.4",
        assembled=[{"metadata": {}, "record_metadata": {}}, {"metadata": {}, "record_metadata": {}}],
        skipped=[
            {"kind": "no_text_pages", "pages": [1], "table_id": "", "caption": ""},
            skipped_table([4, 5], "Sales by region", "a"),
            {"kind": "unreadable_table", "pages": [6], "table_id": "u", "caption": ""},
            skipped_table([3], "", "c"),
        ],
    )
    seen = pause_at(monkeypatch, "index")
    # When the run pauses and the user chooses to index
    result = nodes.ask_skipped(state, deps)
    # Then the question names N = 2 and only the skipped tables
    assert seen["question"] == {
        "pause": "ask_skipped",
        "intro": "There was a problem processing these tables in your PDF:",
        "bullets": ["pages 4\u20135: Sales by region", "page 3"],
        "question": "Index the other 2 tables, or cancel?",
        "choices": [
            {"value": "cancel", "label": "Cancel ingestion"},
            {"value": "index", "label": "Index 2"},
        ],
    }
    assert result == {}


def test_ask_skipped_uses_the_singular_for_one_table(make_settings, monkeypatch) -> None:
    """FR-134: with one table left, the question says "1 table" and the button says "Index 1"."""
    deps, _scripted = make_deps(make_settings)
    state = open_run(
        deps,
        b"%PDF-1.4",
        assembled=[{"metadata": {}, "record_metadata": {}}],
        skipped=[skipped_table([4, 5], "Sales by region")],
    )
    seen = pause_at(monkeypatch, "index")
    # When the run pauses
    result = nodes.ask_skipped(state, deps)
    # Then the wording is singular
    assert seen["question"]["question"] == "Index the other 1 table, or cancel?"
    assert seen["question"]["choices"] == [
        {"value": "cancel", "label": "Cancel ingestion"},
        {"value": "index", "label": "Index 1"},
    ]
    assert seen["question"]["bullets"] == ["pages 4\u20135: Sales by region"]
    assert result == {}


def test_ask_skipped_with_nothing_left_offers_only_cancel(make_settings, monkeypatch) -> None:
    """FR-134: with nothing left to index, the only choice is Cancel."""
    deps, _scripted = make_deps(make_settings)
    state = open_run(deps, b"%PDF-1.4", assembled=[], skipped=[skipped_table([3], "")])
    seen = pause_at(monkeypatch, "cancel")
    # When the user cancels
    result = nodes.ask_skipped(state, deps)
    # Then the question offers only Cancel and the run ends
    assert seen["question"]["question"] == "No table could be processed. Cancel?"
    assert seen["question"]["choices"] == [{"value": "cancel", "label": "Cancel ingestion"}]
    assert seen["question"]["bullets"] == ["page 3"]
    assert result == {
        "outcome": {
            "status": "cancelled",
            "message": "Ingestion cancelled. Nothing from report.pdf was indexed.",
        }
    }


def test_ask_skipped_rejects_index_when_nothing_is_left(make_settings, monkeypatch) -> None:
    """FR-134: Index is not a legal answer when no table can be indexed."""
    deps, _scripted = make_deps(make_settings)
    state = open_run(deps, b"%PDF-1.4", assembled=[], skipped=[skipped_table([3], "")])
    pause_at(monkeypatch, "index")
    # When the pause is resumed with Index anyway
    # Then the node refuses it
    with pytest.raises(ValueError):
        nodes.ask_skipped(state, deps)


def test_ask_skipped_cancel_ends_the_run(make_settings, monkeypatch) -> None:
    """FR-135: Cancel ingestion writes nothing and says the ingestion was cancelled."""
    deps, scripted = make_deps(make_settings)
    state = open_run(
        deps,
        b"%PDF-1.4",
        assembled=[{"metadata": {}, "record_metadata": {}}],
        skipped=[skipped_table([4], "Sales")],
    )
    pause_at(monkeypatch, "cancel")
    # When the user cancels
    result = nodes.ask_skipped(state, deps)
    # Then the run is cancelled and nothing was called
    assert result["outcome"]["status"] == "cancelled"
    assert result["outcome"]["message"] == "Ingestion cancelled. Nothing from report.pdf was indexed."
    assert scripted.calls == [] and deps.embeddings.calls == [] and deps.index.calls == []


# --- index --------------------------------------------------------------------------------------


def test_index_reports_how_many_tables_were_stored(make_settings, table_store_dir) -> None:
    """FR-144: a successful index says how many tables were stored, singular when there is one."""
    # Given one valid table, then two
    one = sales_table()
    deps, _scripted = make_deps(make_settings)
    state = place_table(deps, one, assembled=[assembled_item(one)])
    # When it is indexed
    single = nodes.index(state, deps)
    # Then the chat names one table and the file was written
    assert single == {"outcome": {"status": "indexed", "message": "Indexed 1 table from report.pdf"}}
    assert (table_store_dir / f"{one.table_id}.parquet").is_file()

    other = sales_table(table_id="0123456789abcdef-p2-t1", pages=(2,))
    deps, _scripted = make_deps(make_settings)
    state = place_table(deps, one, assembled=[assembled_item(one), assembled_item(other)])
    deps.runs.get(THREAD).tables[other.table_id] = other
    # When both are indexed
    plural = nodes.index(state, deps)
    # Then the chat names two tables, with no final period on either sentence
    assert plural == {"outcome": {"status": "indexed", "message": "Indexed 2 tables from report.pdf"}}
    assert not single["outcome"]["message"].endswith(".")
    assert not plural["outcome"]["message"].endswith(".")


def test_index_says_when_the_previous_version_could_not_be_removed(make_settings, table_store_dir) -> None:
    """FR-140: a failed removal of the previous version keeps the new one and says so."""
    # Given an older record for the same file, and a delete that fails
    extracted = sales_table()
    index = FakePineconeIndex(fail_on="delete")
    deps, _scripted = make_deps(make_settings, index=index)
    state = place_table(deps, extracted, assembled=[assembled_item(extracted)])
    index.put(deps.settings.PINECONE_NAMESPACE, "old-id", {"source_file": FILE, "table_id": "old-id"})
    # When the table is indexed
    result = nodes.index(state, deps)
    # Then the new version counts as indexed and the chat asks for a clean upload
    assert result == {
        "outcome": {
            "status": "indexed",
            "message": (
                "report.pdf was indexed, but its previous version couldn't be fully removed. "
                "Upload it again to clean up."
            ),
        }
    }
    assert (table_store_dir / f"{extracted.table_id}.parquet").is_file()


def test_index_uses_the_fixed_sentence_when_storing_fails(make_settings, table_store_dir) -> None:
    """FR-139 (BR-106): a failure while storing uses the FR-139 sentence, never the error's own text."""
    # Given embeddings that cannot be reached
    extracted = sales_table()
    deps, _scripted = make_deps(
        make_settings, embeddings=FakeEmbeddings(error=openai_connection_error())
    )
    state = place_table(deps, extracted, assembled=[assembled_item(extracted)])
    # When the table is indexed
    result = nodes.index(state, deps)
    # Then the chat shows the fixed sentence and nothing was written
    message = result["outcome"]["message"]
    assert result["outcome"]["status"] == "failed"
    assert message == "Couldn't index report.pdf. Your previous version is unchanged."
    for banned in ("LiteLLM", "proxy", "Pinecone"):
        assert banned not in message
    assert list(table_store_dir.glob("*")) == []


def test_index_says_when_the_pdf_has_no_tables(make_settings, table_store_dir, monkeypatch) -> None:
    """FR-142: a PDF with no tables is reported as such, and nothing is written or deleted."""
    deps, _scripted = make_deps(make_settings)
    state = open_run(deps, b"%PDF-1.4", tables=[], assembled=[], skipped=[])
    refuse_write(monkeypatch)
    # When there is nothing to index
    result = nodes.index(state, deps)
    # Then the chat says no tables were found
    assert result == {"outcome": {"status": "no_tables", "message": "I didn't find any tables in report.pdf."}}
    assert deps.embeddings.calls == [] and deps.index.calls == []
    assert list(table_store_dir.glob("*")) == []


def test_index_says_when_every_table_was_skipped(make_settings, table_store_dir, monkeypatch) -> None:
    """FR-142: tables that were all unreadable or skipped produce the nothing-indexed sentence."""
    deps, _scripted = make_deps(make_settings)
    state = open_run(
        deps,
        b"%PDF-1.4",
        tables=[],
        assembled=[],
        skipped=[{"kind": "unreadable_table", "pages": [7], "table_id": "tid", "caption": ""}],
    )
    refuse_write(monkeypatch)
    # When there is nothing left to index
    result = nodes.index(state, deps)
    # Then the chat says no table could be indexed, which is not the "no tables" sentence
    assert result == {
        "outcome": {
            "status": "nothing_indexed",
            "message": "I couldn't index any table from report.pdf.",
        }
    }
    assert deps.embeddings.calls == [] and deps.index.calls == []
    assert list(table_store_dir.glob("*")) == []
