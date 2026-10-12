"""Routers, recursion limit and run control of the ingestion graph (spec 01 §7)."""

from collections.abc import Callable

import pytest
from langgraph.errors import GraphRecursionError
from langgraph.graph import END
from langgraph.types import interrupt

from agents.ingestion import nodes
from agents.ingestion.graph import (
    NODE_NAMES,
    build_graph,
    recursion_limit,
    resume_ingestion,
    route_after_ask_skipped,
    route_after_ask_unreadable,
    route_after_context,
    route_after_enrich,
    route_after_extract,
    route_after_load,
    route_after_next_table,
    route_after_validate,
    run_ingestion,
    table_upper_bound,
)
from agents.ingestion.pdf.document import open_document
from agents.ingestion.pdf.tables import document_sha
from agents.ingestion.state import IngestionDeps, PauseQuestion
from tests.pdf_fixtures import Page, make_pdf, paragraph, table

QUESTION: PauseQuestion = {
    "pause": "ask_unreadable",
    "intro": "I couldn't read some parts of report.pdf:",
    "bullets": ["page 2 (no selectable text)"],
    "question": "They won't be indexed. Continue with the rest, or cancel?",
    "choices": [
        {"value": "cancel", "label": "Cancel ingestion"},
        {"value": "continue", "label": "Continue"},
    ],
}

_CANCELLED = {"status": "cancelled", "message": "Ingestion cancelled. Nothing from report.pdf was indexed."}


def _deps(settings) -> IngestionDeps:
    return IngestionDeps(settings, embeddings=None, index=None)


def _part(kind: str) -> dict:
    return {"kind": kind, "pages": [1], "table_id": "t1", "caption": "Sales"}


def _pdf() -> bytes:
    return make_pdf(Page(blocks=(paragraph("Hello"),)))


def _unexpected(name: str) -> Callable:
    def node(state: dict, deps: IngestionDeps) -> dict:
        raise AssertionError(f"{name} should not run")

    return node


def _install(monkeypatch: pytest.MonkeyPatch, implementations: dict[str, Callable]) -> None:
    for name in NODE_NAMES:
        monkeypatch.setattr(nodes, name, implementations.get(name, _unexpected(name)))


def _spy(monkeypatch: pytest.MonkeyPatch, graph):
    payloads: list = []
    configs: list = []
    original = graph.stream

    def spy(payload, config, *args, **kwargs):
        payloads.append(payload)
        configs.append(config)
        return original(payload, config, *args, **kwargs)

    monkeypatch.setattr(graph, "stream", spy)
    return payloads, configs


def _outcome(status: str) -> dict:
    return {"outcome": {"status": status, "message": "done"}}


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        pytest.param(_outcome("failed"), END, id="outcome-set"),
        pytest.param({}, "extract_tables", id="no-outcome"),
    ],
)
def test_load_ends_the_run_when_the_file_is_refused(state: dict, expected: str) -> None:
    """FR-105: an outcome set while opening the PDF ends the run; otherwise the tables are extracted."""
    # Given a state after load_pdf / When the router chooses / Then the next step matches
    assert route_after_load(state) == expected


@pytest.mark.parametrize(
    ("kinds", "expected"),
    [
        pytest.param(["no_text_pages"], "ask_unreadable", id="pages-without-text"),
        pytest.param(["unreadable_table"], "ask_unreadable", id="unreadable-table"),
        pytest.param(["no_text_pages", "unreadable_table"], "ask_unreadable", id="both"),
        pytest.param(["table"], "collect_context", id="skipped-table-only"),
        pytest.param([], "collect_context", id="nothing-skipped"),
    ],
)
def test_extraction_pauses_only_for_unreadable_parts(kinds: list[str], expected: str) -> None:
    """FR-119: pages without text or an unreadable table pause; other skipped parts do not."""
    # Given the skipped parts extraction recorded
    state = {"skipped": [_part(kind) for kind in kinds]}

    # When the router chooses / Then unreadable parts pause and the rest continue
    assert route_after_extract(state) == expected


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        pytest.param({"outcome": _CANCELLED}, END, id="cancelled"),
        pytest.param({}, "collect_context", id="continued"),
    ],
)
def test_cancelling_the_unreadable_pause_ends_the_run(state: dict, expected: str) -> None:
    """FR-120: cancel ends the run; continuing collects the table context."""
    # Given the answer to the unreadable pause / When the router chooses
    assert route_after_ask_unreadable(state) == expected


@pytest.mark.parametrize(
    ("tables", "expected"),
    [
        pytest.param([], "index", id="no-tables"),
        pytest.param([{"table_id": "t1"}], "enrich", id="one-table"),
    ],
)
def test_a_pdf_with_zero_tables_goes_straight_to_index(tables: list, expected: str) -> None:
    """FR-142: zero Tables after extraction go to index; any Table is enriched."""
    # Given the tables extraction kept
    assert route_after_context({"tables": tables}) == expected


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        pytest.param(_outcome("failed"), END, id="llm-failure"),
        pytest.param({}, "validate", id="answer-received"),
    ],
)
def test_an_enrich_failure_ends_the_run(state: dict, expected: str) -> None:
    """FR-160: an outcome set by enrich ends the run; an answer is validated."""
    assert route_after_enrich(state) == expected


@pytest.mark.parametrize(
    ("attempts", "max_retries", "feedback", "expected"),
    [
        pytest.param(2, 2, ["The name is empty."], "enrich", id="attempts-equal-retries"),
        pytest.param(3, 2, ["The name is empty."], "next_table", id="attempts-past-retries"),
        pytest.param(1, 0, ["The name is empty."], "next_table", id="retries-zero-after-one-attempt"),
        pytest.param(0, 0, ["The name is empty."], "enrich", id="retries-zero-before-an-attempt"),
        pytest.param(2, 2, [], "next_table", id="valid-answer"),
    ],
)
def test_feedback_retries_until_the_attempt_passes_the_limit(
    attempts: int, max_retries: int, feedback: list[str], expected: str
) -> None:
    """FR-132: feedback retries while attempts <= max_retries; the next attempt moves on. FR-133: no feedback moves on."""
    # Given the attempt count and the feedback validate just wrote
    state = {"attempts": attempts, "max_retries": max_retries, "feedback": feedback}

    # When the router chooses / Then the Table is retried or left behind
    assert route_after_validate(state) == expected


def test_the_next_table_keeps_enriching_until_the_last_one() -> None:
    """FR-133: while tables remain, the run enriches the next one."""
    # Given two tables and the cursor still on the first
    state = {"current": 0, "tables": [{"table_id": "t1"}, {"table_id": "t2"}], "skipped": [_part("table")]}

    # When the router chooses / Then enrichment continues even if a table was already skipped
    assert route_after_next_table(state) == "enrich"


@pytest.mark.parametrize(
    ("skipped", "expected"),
    [
        pytest.param([_part("table")], "ask_skipped", id="skipped-table"),
        pytest.param([_part("no_text_pages")], "index", id="unreadable-part-only"),
        pytest.param([], "index", id="nothing-skipped"),
    ],
)
def test_a_skipped_table_pauses_once_every_table_is_done(skipped: list[dict], expected: str) -> None:
    """FR-134: after the last Table, a skipped Table pauses; otherwise the run indexes."""
    # Given the cursor past the only table
    state = {"current": 1, "tables": [{"table_id": "t1"}], "skipped": skipped}

    # When the router chooses
    assert route_after_next_table(state) == expected


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        pytest.param({"outcome": _CANCELLED}, END, id="cancelled"),
        pytest.param({}, "index", id="index-the-rest"),
    ],
)
def test_cancelling_the_skipped_pause_ends_the_run(state: dict, expected: str) -> None:
    """FR-135: cancel ends the run; indexing the rest goes to index."""
    assert route_after_ask_skipped(state) == expected


def test_recursion_limit_grows_with_the_tables_and_the_retries() -> None:
    """FR-143: the limit is 10 + T × (2 × (R + 1) + 1)."""
    # Given table counts and retry limits / When the limit is computed
    assert recursion_limit(0, 2) == 10
    assert recursion_limit(6, 2) == 52
    assert recursion_limit(1, 0) == 13


def test_table_upper_bound_counts_every_table_pymupdf_finds() -> None:
    """S01-D-023: the bound is how many tables PyMuPDF finds, plus the page count."""
    # Given a two-page PDF with one table on each page
    pdf = make_pdf(
        Page(blocks=(paragraph("Intro"), table(["A", "B"], [["1", "2"]]))),
        Page(blocks=(table(["C", "D"], [["3", "4"]]),)),
    )

    # When the bound is read / Then both tables and both pages are counted
    assert table_upper_bound(pdf) == (2, 2)


def test_a_file_that_cannot_be_opened_has_no_tables() -> None:
    """S01-D-023: a file open_document refuses contributes no tables and no pages."""
    # Given bytes that are not a PDF / When the bound is read / Then the run can still start
    assert table_upper_bound(b"not a pdf") == (0, 0)


def test_table_upper_bound_closes_the_document(monkeypatch: pytest.MonkeyPatch) -> None:
    """S01-D-023: the document opened to count tables is closed before returning."""
    # Given a readable PDF whose open document we can see
    pdf = _pdf()
    opened: list = []
    real_open = open_document

    def spy(data: bytes):
        document = real_open(data)
        opened.append(document)
        return document

    monkeypatch.setattr("agents.ingestion.graph.open_document", spy)

    # When the bound is read / Then the document is closed
    table_upper_bound(pdf)
    assert opened[0].is_closed


def test_a_run_reports_node_updates_in_order(make_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-153: each finished node is reported in order, and a node that changes nothing reports an empty update."""
    # Given a PDF whose fake nodes find no tables
    settings = make_settings()
    deps = _deps(settings)
    pdf = _pdf()
    seen: dict = {}

    def load_pdf(state, deps):
        seen["state"] = dict(state)
        seen["pdf"] = deps.runs.get(state["thread_id"]).pdf
        return {"document_sha": "sha", "page_count": 1}

    def extract_tables(state, deps):
        return {"tables": []}

    def collect_context(state, deps):
        return {}

    def index(state, deps):
        return {"outcome": {"status": "no_tables", "message": "I didn't find any tables in report.pdf."}}

    _install(
        monkeypatch,
        {
            "load_pdf": load_pdf,
            "extract_tables": extract_tables,
            "collect_context": collect_context,
            "index": index,
        },
    )
    graph = build_graph(deps)
    updates: list[tuple[str, dict]] = []

    # When the run streams
    result = run_ingestion(
        graph, deps, "report.pdf", pdf, thread_id="thread-1", on_update=lambda name, update: updates.append((name, update))
    )

    # Then the nodes run in order, the input state is the contract's, and the bytes stayed in the store
    assert updates == [
        ("load_pdf", {"document_sha": "sha", "page_count": 1}),
        ("extract_tables", {"tables": []}),
        ("collect_context", {}),
        ("index", {"outcome": {"status": "no_tables", "message": "I didn't find any tables in report.pdf."}}),
    ]
    assert seen["state"]["thread_id"] == "thread-1"
    assert seen["state"]["source_file"] == "report.pdf"
    assert seen["state"]["max_retries"] == settings.INGESTION_MAX_RETRIES
    assert seen["state"]["assembled"] == []
    assert seen["state"]["skipped"] == []
    assert seen["pdf"] == pdf
    assert result.status == "finished"
    assert result.question is None
    assert result.thread_id == "thread-1"


def test_a_finished_run_closes_the_store_and_cannot_be_resumed(make_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    """BR-111: once the run ends, the per-run store is empty. A finished thread cannot be resumed."""
    # Given a run that indexes nothing
    settings = make_settings()
    deps = _deps(settings)
    pdf = _pdf()
    _install(
        monkeypatch,
        {
            "load_pdf": lambda state, deps: {"document_sha": document_sha(pdf), "page_count": 1},
            "extract_tables": lambda state, deps: {"tables": []},
            "collect_context": lambda state, deps: {},
            "index": lambda state, deps: {"outcome": {"status": "no_tables", "message": "none"}},
        },
    )
    graph = build_graph(deps)
    payloads, configs = _spy(monkeypatch, graph)

    # When it finishes without a caller-supplied thread id
    result = run_ingestion(graph, deps, "report.pdf", pdf)

    # Then the store is empty, the limit came from the pre-run count, and resume is refused
    assert result.status == "finished"
    assert len(result.thread_id) == 32
    assert int(result.thread_id, 16) >= 0
    assert deps.runs.thread_ids() == []
    assert configs[0]["recursion_limit"] == recursion_limit(0, settings.INGESTION_MAX_RETRIES)
    assert configs[0]["metadata"]["pages"] == 1
    assert configs[0]["metadata"]["document_sha"] == document_sha(pdf)
    assert configs[0]["configurable"]["thread_id"] == result.thread_id
    assert payloads[0]["thread_id"] == result.thread_id
    with pytest.raises(ValueError):
        resume_ingestion(graph, deps, result.thread_id, "continue")


def test_an_unreadable_part_pauses_and_keeps_the_store(make_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-119: an unreadable part pauses the run with the interrupt value, and the store stays open."""
    # Given a run whose extraction finds an unreadable part
    deps = _deps(make_settings())
    pdf = _pdf()
    updates: list[str] = []

    def ask_unreadable(state, deps):
        interrupt(QUESTION)
        return {}

    _install(
        monkeypatch,
        {
            "load_pdf": lambda state, deps: {"document_sha": "sha", "page_count": 1},
            "extract_tables": lambda state, deps: {
                "tables": [{"table_id": "t1"}],
                "skipped": [_part("no_text_pages")],
                "current": 0,
                "attempts": 0,
                "feedback": [],
            },
            "ask_unreadable": ask_unreadable,
        },
    )
    graph = build_graph(deps)

    # When the run streams
    result = run_ingestion(
        graph, deps, "report.pdf", pdf, thread_id="thread-1", on_update=lambda name, update: updates.append(name)
    )

    # Then it is paused on that question and the bytes are still stored
    assert result.status == "paused"
    assert result.question == QUESTION
    assert result.thread_id == "thread-1"
    assert updates == ["load_pdf", "extract_tables"]
    assert deps.runs.thread_ids() == ["thread-1"]
    assert deps.runs.get("thread-1").pdf == pdf


def test_continue_resumes_the_same_thread_and_then_closes_the_store(
    make_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-120: Continue resumes the paused run; when it finishes, the store is closed."""
    # Given a run paused on an unreadable part, with one table left
    settings = make_settings()
    deps = _deps(settings)
    pdf = _pdf()

    def ask_unreadable(state, deps):
        choice = interrupt(QUESTION)
        if choice == "cancel":
            return {"outcome": _CANCELLED}
        return {}

    _install(
        monkeypatch,
        {
            "load_pdf": lambda state, deps: {"document_sha": "sha", "page_count": 1},
            "extract_tables": lambda state, deps: {
                "tables": [{"table_id": "t1"}],
                "skipped": [_part("no_text_pages")],
                "current": 0,
                "attempts": 0,
                "feedback": [],
            },
            "ask_unreadable": ask_unreadable,
            "collect_context": lambda state, deps: {},
            "enrich": lambda state, deps: {"attempts": 1, "answer": {}},
            "validate": lambda state, deps: {"feedback": []},
            "next_table": lambda state, deps: {"current": 1, "attempts": 0, "feedback": [], "answer": None},
            "index": lambda state, deps: {"outcome": {"status": "indexed", "message": "Indexed 1 table from report.pdf."}},
        },
    )
    graph = build_graph(deps)
    payloads, configs = _spy(monkeypatch, graph)
    updates: list[str] = []
    paused = run_ingestion(
        graph, deps, "report.pdf", pdf, thread_id="thread-1", on_update=lambda name, update: updates.append(name)
    )

    # When the user continues
    updates.clear()
    finished = resume_ingestion(graph, deps, "thread-1", "continue", on_update=lambda name, update: updates.append(name))

    # Then the same thread runs on to index and the store is empty
    assert paused.status == "paused"
    assert payloads[1].resume == "continue"
    assert configs[1]["configurable"]["thread_id"] == "thread-1"
    assert updates == ["ask_unreadable", "collect_context", "enrich", "validate", "next_table", "index"]
    assert finished.status == "finished"
    assert finished.question is None
    assert finished.values["outcome"]["status"] == "indexed"
    assert deps.runs.thread_ids() == []


def test_cancel_ends_the_run_without_indexing(make_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    """BR-103: Cancel at the unreadable pause ends the run without reaching index."""
    # Given a paused run
    deps = _deps(make_settings())
    pdf = _pdf()

    def ask_unreadable(state, deps):
        choice = interrupt(QUESTION)
        if choice == "cancel":
            return {"outcome": _CANCELLED}
        return {}

    _install(
        monkeypatch,
        {
            "load_pdf": lambda state, deps: {"document_sha": "sha", "page_count": 1},
            "extract_tables": lambda state, deps: {
                "tables": [{"table_id": "t1"}],
                "skipped": [_part("no_text_pages")],
            },
            "ask_unreadable": ask_unreadable,
        },
    )
    graph = build_graph(deps)
    run_ingestion(graph, deps, "report.pdf", pdf, thread_id="thread-1")
    updates: list[str] = []

    # When the user cancels
    result = resume_ingestion(graph, deps, "thread-1", "cancel", on_update=lambda name, update: updates.append(name))

    # Then the run is finished as cancelled and index never ran
    assert result.status == "finished"
    assert result.values["outcome"] == _CANCELLED
    assert updates == ["ask_unreadable"]
    assert deps.runs.thread_ids() == []


def test_an_exception_closes_the_store(make_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    """BR-111: an exception during the run closes the per-run store and is raised again."""
    # Given a node that fails
    deps = _deps(make_settings())
    pdf = _pdf()

    def load_pdf(state, deps):
        raise RuntimeError("broken pdf")

    _install(monkeypatch, {"load_pdf": load_pdf})
    graph = build_graph(deps)

    # When the run streams / Then the error escapes and the store is empty
    with pytest.raises(RuntimeError, match="broken pdf"):
        run_ingestion(graph, deps, "report.pdf", pdf, thread_id="thread-1")
    assert deps.runs.thread_ids() == []


def test_resume_refuses_a_thread_that_is_not_paused(make_settings) -> None:
    """FR-145: resume raises when the thread is unknown or open but not waiting at a pause."""
    # Given a store that holds one run the graph never paused
    deps = _deps(make_settings())
    graph = build_graph(deps)
    deps.runs.open("thread-1", b"%PDF")

    # When resume is asked for that thread and for an unknown one / Then both are refused
    with pytest.raises(ValueError):
        resume_ingestion(graph, deps, "missing", "cancel")
    with pytest.raises(ValueError):
        resume_ingestion(graph, deps, "thread-1", "continue")
    assert deps.runs.thread_ids() == ["thread-1"]


def test_six_tables_that_fail_every_attempt_finish_within_the_recursion_limit(
    make_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """VC-146: 6 Tables, every attempt failing, R = 2, finishes at recursion_limit(6, 2); a smaller limit raises."""
    # Given fake nodes that fail every attempt of six tables
    deps = _deps(make_settings(INGESTION_MAX_RETRIES="2"))
    calls: list[str] = []

    def record(name: str, update: dict) -> Callable:
        def node(state, deps):
            calls.append(name)
            return update

        return node

    def enrich(state, deps):
        calls.append("enrich")
        return {"attempts": state["attempts"] + 1, "answer": {"name": "x"}}

    def validate(state, deps):
        calls.append("validate")
        update: dict = {"feedback": ["The name is empty."]}
        if state["attempts"] > state["max_retries"]:
            table = state["tables"][state["current"]]
            update["skipped"] = [_part("table") | {"table_id": table["table_id"], "pages": table["pages"]}]
        return update

    def next_table(state, deps):
        calls.append("next_table")
        return {"current": state["current"] + 1, "attempts": 0, "feedback": [], "answer": None}

    def extract_tables(state, deps):
        calls.append("extract_tables")
        return {
            "tables": [{"table_id": f"t{i}", "pages": [i + 1]} for i in range(6)],
            "current": 0,
            "attempts": 0,
            "feedback": [],
            "answer": None,
        }

    _install(
        monkeypatch,
        {
            "load_pdf": record("load_pdf", {"document_sha": "sha", "page_count": 6}),
            "extract_tables": extract_tables,
            "collect_context": record("collect_context", {}),
            "enrich": enrich,
            "validate": validate,
            "next_table": next_table,
            "ask_skipped": record("ask_skipped", {}),
            "index": record("index", {"outcome": {"status": "indexed", "message": "done"}}),
        },
    )
    graph = build_graph(deps)
    initial = {
        "thread_id": "six",
        "source_file": "report.pdf",
        "max_retries": 2,
        "assembled": [],
        "skipped": [],
    }

    # When it streams at the formula's limit
    config = {"recursion_limit": recursion_limit(6, 2), "configurable": {"thread_id": "six"}}
    for _chunk in graph.stream(initial, config, stream_mode="updates"):
        pass
    snapshot = graph.get_state(config)

    # Then every attempt ran and the run finished
    assert calls.count("enrich") == 18
    assert calls.count("validate") == 18
    assert calls.count("next_table") == 6
    assert calls.count("ask_skipped") == 1
    assert calls.count("index") == 1
    assert snapshot.values["outcome"]["status"] == "indexed"
    assert snapshot.interrupts == ()

    # When the same loop is given a limit too small for six tables / Then it cannot finish
    with pytest.raises(GraphRecursionError):
        for _chunk in graph.stream(
            dict(initial),
            {"recursion_limit": 8, "configurable": {"thread_id": "too-small"}},
            stream_mode="updates",
        ):
            pass
