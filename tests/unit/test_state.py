"""The shared pieces of the ingestion graph: the per-run store, the deps and the pause text (BR-111)."""

import pytest

from agents.ingestion.pdf.document import open_document
from agents.ingestion.state import IngestionDeps, PauseQuestion, RunStore, make_deps, question_text
from services.llm import make_chat_model
from tests.pdf_fixtures import Page, make_pdf, paragraph
from tests.stubs import FakeEmbeddings, StubPineconeClient


def test_a_run_holds_its_bytes_until_it_is_closed() -> None:
    """VC-167 (store part): the bytes live in the store, keyed by thread id, and are dropped on close."""
    # Given an empty store
    runs = RunStore()

    # When a run is opened
    data = runs.open("thread-1", b"%PDF-1.7 fake")

    # Then it can be read back by its thread id, and closing it empties the store
    assert runs.get("thread-1") is data
    assert data.pdf == b"%PDF-1.7 fake"
    assert runs.thread_ids() == ["thread-1"]
    runs.close("thread-1")
    assert runs.thread_ids() == []


def test_closing_a_run_closes_its_document_and_is_idempotent() -> None:
    """VC-167 (store part): the open document is closed with the run; closing twice is harmless."""
    # Given a run whose document is open
    runs = RunStore()
    pdf = make_pdf(Page([paragraph("Hello")]))
    data = runs.open("thread-1", pdf)
    data.document = open_document(pdf)

    # When it is closed twice
    runs.close("thread-1")
    runs.close("thread-1")

    # Then the document is closed and the store is empty
    assert data.document.is_closed
    assert runs.thread_ids() == []


def test_opening_the_same_thread_twice_is_refused() -> None:
    """BR-111: one thread id is one run."""
    # Given a store with an open run
    runs = RunStore()
    runs.open("thread-1", b"a")

    # When the same thread id is opened again / an unknown one is read
    # Then both are errors
    with pytest.raises(ValueError):
        runs.open("thread-1", b"b")
    with pytest.raises(KeyError):
        runs.get("thread-2")


def test_question_text_joins_intro_bullets_and_question() -> None:
    """FR-119: the pause text is the intro line, one bullet per part, then the question."""
    # Given a pause question
    question: PauseQuestion = {
        "pause": "ask_unreadable",
        "intro": "I couldn't read some parts of report.pdf:",
        "bullets": ["pages 2–3 (no selectable text)", "a table on page 7"],
        "question": "They won't be indexed. Continue with the rest, or cancel?",
        "choices": [{"value": "cancel", "label": "Cancel ingestion"}, {"value": "continue", "label": "Continue"}],
    }

    # When it is printed / Then the lines are in order
    assert question_text(question) == (
        "I couldn't read some parts of report.pdf:\n"
        "- pages 2–3 (no selectable text)\n"
        "- a table on page 7\n"
        "They won't be indexed. Continue with the rest, or cancel?"
    )


def test_make_deps_builds_the_production_dependencies(make_settings) -> None:
    """FR-127: the chat model comes from `make_chat_model` (LLM_MODEL); the index from the index host."""
    # Given settings and a Pinecone client that hands out a fake index
    settings = make_settings()
    client = StubPineconeClient(index=(1536, "cosine"))
    client.opened_index = object()

    # When the production deps are built
    deps = make_deps(settings, client=client)

    # Then each dependency is the production one, and every run store starts empty
    assert isinstance(deps, IngestionDeps)
    assert deps.index is client.opened_index
    assert deps.make_chat_model is make_chat_model
    assert deps.runs.thread_ids() == []
    assert IngestionDeps(settings, embeddings=FakeEmbeddings(), index=None).runs is not deps.runs
