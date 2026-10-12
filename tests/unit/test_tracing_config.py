"""Run labels and the tracing scope of one ingestion run (FR-153, FR-154, BR-107)."""

import os
from collections.abc import Callable
from uuid import UUID

import pytest
from langgraph.types import Command, interrupt
from langsmith.run_helpers import get_tracing_context

from agents.ingestion import nodes
from agents.ingestion.graph import NODE_NAMES, build_graph, recursion_limit, resume_ingestion, run_config, run_ingestion, tracing_scope
from agents.ingestion.pdf.tables import document_sha
from agents.ingestion.state import IngestionDeps, PauseQuestion
from tests.pdf_fixtures import Page, make_pdf, paragraph
from tests.stubs import FAKE_LANGSMITH_KEY, FAKE_LITELLM_KEY, FAKE_PINECONE_KEY, StubLangSmithClient

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


def _deps(settings) -> IngestionDeps:
    return IngestionDeps(settings, embeddings=None, index=None)


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


def _clear_langsmith_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.startswith("LANGSMITH_"):
            monkeypatch.delenv(name, raising=False)


def test_run_config_labels_one_ingestion(make_settings) -> None:
    """VC-156: the graph config holds the run name, the ingestion tag, the six metadata keys and a run_id."""
    # Given the settings of a run of report.pdf
    settings = make_settings(INGESTION_MAX_RETRIES="2")

    # When the config is built, and built again with an explicit run id
    config = run_config(
        settings,
        source_file="report.pdf",
        document_sha="abc123",
        pages=4,
        thread_id="thread-1",
        limit=52,
    )
    another = run_config(
        settings,
        source_file="report.pdf",
        document_sha="abc123",
        pages=4,
        thread_id="thread-1",
        limit=52,
    )
    supplied = run_config(
        settings,
        source_file="report.pdf",
        document_sha="abc123",
        pages=4,
        thread_id="thread-1",
        limit=52,
        run_id="given-run",
    )

    # Then the labels are exactly those of FR-153, and each call gets its own run id unless one is given
    assert set(config) == {"run_name", "tags", "metadata", "run_id", "configurable", "recursion_limit"}
    assert config["run_name"] == "Ingestion: report.pdf"
    assert config["tags"] == ["ingestion"]
    assert config["metadata"] == {
        "source_file": "report.pdf",
        "document_sha": "abc123",
        "pages": 4,
        "llm_model": settings.LLM_MODEL,
        "max_retries": 2,
        "thread_id": "thread-1",
    }
    assert isinstance(config["run_id"], UUID)
    assert isinstance(another["run_id"], UUID)
    assert config["run_id"] != another["run_id"]
    assert supplied["run_id"] == "given-run"
    assert config["configurable"] == {"thread_id": "thread-1"}
    assert config["recursion_limit"] == 52


def test_a_resumed_run_keeps_the_same_thread_id(make_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    """VC-156: the resumed call after a pause carries the same thread_id, rebuilt from the saved state."""
    # Given a run paused after extraction, with tracing left off so no client is built
    settings = make_settings(INGESTION_MAX_RETRIES="2")
    deps = _deps(settings)
    pdf = _pdf()

    def explode(settings):
        raise AssertionError("LangSmith client constructed while tracing is off")

    monkeypatch.setattr("agents.ingestion.graph.make_langsmith_client", explode, raising=False)

    def ask_unreadable(state, deps):
        choice = interrupt(QUESTION)
        if choice == "cancel":
            return {"outcome": {"status": "cancelled", "message": "cancelled"}}
        return {}

    _install(
        monkeypatch,
        {
            "load_pdf": lambda state, deps: {"document_sha": "from-state", "page_count": 7},
            "extract_tables": lambda state, deps: {
                "tables": [{"table_id": "t1", "pages": [1]}],
                "skipped": [{"kind": "no_text_pages", "pages": [2], "table_id": "", "caption": ""}],
                "current": 0,
                "attempts": 0,
                "feedback": [],
            },
            "ask_unreadable": ask_unreadable,
            "collect_context": lambda state, deps: {},
            "enrich": lambda state, deps: {"outcome": {"status": "indexed", "message": "done"}},
        },
    )
    graph = build_graph(deps)
    payloads, configs = _spy(monkeypatch, graph)

    # When the run pauses and is then resumed
    paused = run_ingestion(graph, deps, "report.pdf", pdf, thread_id="thread-vc156")
    finished = resume_ingestion(graph, deps, "thread-vc156", "continue")

    # Then both calls use that thread, and the resume metadata comes from the saved state
    assert paused.status == "paused"
    assert finished.status == "finished"
    assert isinstance(payloads[1], Command)
    assert payloads[1].resume == "continue"
    started, resumed = configs
    assert started["run_name"] == "Ingestion: report.pdf"
    assert started["tags"] == ["ingestion"]
    assert set(started["metadata"]) == {
        "source_file",
        "document_sha",
        "pages",
        "llm_model",
        "max_retries",
        "thread_id",
    }
    assert started["metadata"]["document_sha"] == document_sha(pdf)
    assert started["metadata"]["pages"] == 1
    assert started["metadata"]["thread_id"] == "thread-vc156"
    assert started["configurable"]["thread_id"] == "thread-vc156"
    assert started["run_id"] is not None
    assert started["recursion_limit"] == recursion_limit(0, settings.INGESTION_MAX_RETRIES)
    assert resumed["configurable"]["thread_id"] == "thread-vc156"
    assert resumed["metadata"]["thread_id"] == "thread-vc156"
    assert resumed["metadata"]["source_file"] == "report.pdf"
    assert resumed["metadata"]["document_sha"] == "from-state"
    assert resumed["metadata"]["pages"] == 7
    assert resumed["recursion_limit"] == recursion_limit(1, settings.INGESTION_MAX_RETRIES)


def test_tracing_on_uses_the_settings_project_without_env_variables(make_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    """VC-157: tracing on in Settings, with no LANGSMITH_* variable in the environment, traces to LANGSMITH_PROJECT."""
    # Given tracing on in Settings, no LANGSMITH_* variable in the environment, and a stub client
    _clear_langsmith_env(monkeypatch)

    def explode(settings):
        raise AssertionError("a real LangSmith client was constructed")

    monkeypatch.setattr("agents.ingestion.graph.make_langsmith_client", explode, raising=False)
    settings = make_settings(LANGSMITH_TRACING="true", LANGSMITH_PROJECT="octi-from-settings")
    client = StubLangSmithClient()

    # When code runs inside the tracing scope / Then tracing is on for that project, using the stub
    with tracing_scope(settings, client):
        context = get_tracing_context()
        assert context["enabled"] is True
        assert context["project_name"] == settings.LANGSMITH_PROJECT
        assert context["client"] is client


def test_tracing_off_builds_no_client(make_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-154: with tracing off, the scope disables tracing and builds no client."""
    # Given tracing off and a factory that must not be called
    def explode(settings):
        raise AssertionError("client built while tracing is off")

    monkeypatch.setattr("agents.ingestion.graph.make_langsmith_client", explode, raising=False)
    settings = make_settings()

    # When the scope is entered / Then tracing is disabled
    with tracing_scope(settings):
        assert get_tracing_context()["enabled"] is False


def test_a_supplied_client_is_used_when_tracing_is_on(make_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-154: a caller-supplied client is the tracing client; the factory is not called."""
    # Given tracing on and a stub client
    def explode(settings):
        raise AssertionError("factory called even though a client was supplied")

    monkeypatch.setattr("agents.ingestion.graph.make_langsmith_client", explode, raising=False)
    settings = make_settings(LANGSMITH_TRACING="true")
    client = StubLangSmithClient()

    # When the scope is entered with that client / Then the context keeps it
    with tracing_scope(settings, client):
        assert get_tracing_context()["client"] is client
        assert get_tracing_context()["enabled"] is True


def test_tracing_on_without_a_client_uses_the_factory(make_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-154: with tracing on and no client, the scope uses make_langsmith_client(settings)."""
    # Given a factory that returns a sentinel instead of contacting LangSmith
    sentinel = object()
    seen: list = []

    def fake_factory(settings):
        seen.append(settings)
        return sentinel

    monkeypatch.setattr("agents.ingestion.graph.make_langsmith_client", fake_factory, raising=False)
    settings = make_settings(LANGSMITH_TRACING="true")

    # When the scope is entered without a client / Then the factory's client is the tracing client
    with tracing_scope(settings):
        assert get_tracing_context()["client"] is sentinel
        assert get_tracing_context()["project_name"] == settings.LANGSMITH_PROJECT
    assert seen == [settings]


def test_run_config_contains_no_secret(make_settings) -> None:
    """VC-159: fake secrets do not appear in the trace config."""
    # Given settings that hold the fake secrets
    settings = make_settings()

    # When the config is built / Then none of those secrets is in it
    config = run_config(
        settings,
        source_file="report.pdf",
        document_sha="abc123",
        pages=4,
        thread_id="thread-1",
        limit=10,
    )
    text = str(config)
    assert FAKE_LITELLM_KEY not in text
    assert FAKE_PINECONE_KEY not in text
    assert FAKE_LANGSMITH_KEY not in text
