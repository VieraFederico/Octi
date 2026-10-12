"""Small Analyst nodes: planning, retrieval, selection, execution and a checked answer.

Each returns a partial state update. Plain checks decide status and retries; the model supplies
meaning and code, never the final status. Only the sandbox runner executes generated code.
"""

import logging
from dataclasses import asdict
from typing import Any, TypeVar

from langchain_core.exceptions import OutputParserException
from pydantic import BaseModel, ValidationError

from agents.analyst import checks, prompts
from agents.analyst.prelude import make_aliases, prelude_source
from agents.analyst.schemas import (
    AnswerFacts, AttemptCheck, CodeDraft, FinalAnswer, PartSelection, PreviousAttempt,
    QueryPlan, TableSelection, TableSource,
)
from agents.analyst.state import AnalystDeps, AnalystState, AnalysisError
from agents.ingestion.indexing import entry_from_record
from agents.ingestion.schemas import CatalogEntry
from services.errors import LLMProxyError, SandboxError, TableStoreError, VectorStoreError
from services.llm import translate_proxy_errors
from services.sandbox import prepare_run_folder
from services.vector_store import query_records

logger = logging.getLogger(__name__)

WINDOW_TURNS = 4
MAX_SEARCH_PHRASES = 3
TOP_K = 5
MAX_CANDIDATES = 10
SELECTION_RETRIES = 1
NUMBER_RETRIES = 1
NO_TABLES_MESSAGE = "There are no tables in the library yet. Attach a PDF with +."
OUTAGE_MESSAGE = "Something went wrong on my side and I couldn't answer. Please try again in a moment."
CODE_DRAFT_FEEDBACK = "Your answer must be a CodeDraft with non-empty code and approach."
SELECTION_SHAPE_FEEDBACK = "Return a valid TableSelection object with one entry for every question part."

Model = TypeVar("Model", bound=BaseModel)


def _failure(kind: str) -> dict[str, Any]:
    return {"error": {"kind": kind, "message": OUTAGE_MESSAGE}}


def _invoke(schema: type[Model], messages: list, deps: AnalystDeps) -> Model | None:
    """Use the proxy and parsed structured output; parsing failures remain separate from outages."""
    try:
        with translate_proxy_errors():
            model = deps.make_chat_model(deps.settings).with_structured_output(schema, include_raw=True)
            response = model.invoke(messages)
        parsed = response.get("parsed")
        if parsed is None:
            return None
        return schema.model_validate(parsed)
    except (ValidationError, OutputParserException):
        logger.debug("Malformed %s output", schema.__name__, exc_info=True)
        return None


def library_check(state: AnalystState, deps: AnalystDeps) -> dict[str, Any]:
    """Read the provided catalog once, or reload once when it was not loaded (FR-246)."""
    try:
        catalog = deps.catalog if deps.catalog is not None else deps.load_catalog(deps.settings, deps.index)
    except VectorStoreError:
        logger.debug("Catalog reload failed", exc_info=True)
        return _failure("vector_store")
    # Only the library-check outcome passes to the next node, never the catalog itself (D-120).
    return {"answer": NO_TABLES_MESSAGE if not catalog else None}


def no_tables(state: AnalystState, deps: AnalystDeps) -> dict[str, Any]:
    """An empty library is a normal answer with no model call (FR-202)."""
    return {"answer": NO_TABLES_MESSAGE, "answer_status": "cannot_answer", "part_outcomes": [], "error": None}


def understand(state: AnalystState, deps: AnalystDeps) -> dict[str, Any]:
    """Rewrite the latest question using at most four earlier Analysis turns (FR-203/206)."""
    try:
        plan = _invoke(QueryPlan, prompts.build_understand_messages(state["question"], state["window"][-WINDOW_TURNS:]), deps)
    except LLMProxyError:
        logger.debug("Question planning failed", exc_info=True)
        return _failure("llm")
    if plan is None or not plan.parts or not plan.search_phrases:
        return _failure("llm")
    phrases = [phrase for phrase in plan.search_phrases[:MAX_SEARCH_PHRASES] if phrase.strip()]
    if not phrases:
        return _failure("llm")
    return {"plan": plan.model_copy(update={"search_phrases": phrases})}


def retrieve(state: AnalystState, deps: AnalystDeps) -> dict[str, Any]:
    """One search per phrase; merge by table id and keep its best score (FR-207/208)."""
    plan = state["plan"]
    assert plan is not None
    try:
        with translate_proxy_errors():
            embeddings = deps.embeddings if deps.embeddings is not None else deps.make_embeddings(deps.settings)
            vectors = [embeddings.embed_query(phrase) for phrase in plan.search_phrases]
        index = deps.index if deps.index is not None else deps.open_index(deps.settings)
        best: dict[str, tuple[float, CatalogEntry]] = {}
        for vector in vectors:
            for match in query_records(index, deps.settings.PINECONE_NAMESPACE, vector, TOP_K):
                entry = entry_from_record(match["metadata"])
                score = match["score"]
                if entry.table_id not in best or score > best[entry.table_id][0]:
                    best[entry.table_id] = (score, entry)
    except LLMProxyError:
        logger.debug("Search embedding failed", exc_info=True)
        return _failure("llm")
    except VectorStoreError:
        logger.debug("Table retrieval failed", exc_info=True)
        return _failure("vector_store")
    ranked = sorted(best.values(), key=lambda item: item[0], reverse=True)
    return {"candidates": [entry for _, entry in ranked[:MAX_CANDIDATES]]}


def select(state: AnalystState, deps: AnalystDeps) -> dict[str, Any]:
    """Validate selection; one retry, then a missing result for every part (FR-212)."""
    plan = state["plan"]
    assert plan is not None
    count = state["selection_attempts"] + 1
    try:
        selection = _invoke(TableSelection, prompts.build_select_messages(
            plan, state["candidates"], previous=state.get("selection"), feedback=state["selection_feedback"],
        ), deps)
    except LLMProxyError:
        logger.debug("Table selection failed", exc_info=True)
        return _failure("llm")
    feedback = ([SELECTION_SHAPE_FEEDBACK] if selection is None else
                checks.check_selection(selection, plan, [entry.table_id for entry in state["candidates"]]))
    if feedback and count > SELECTION_RETRIES:
        selection = TableSelection(parts=[PartSelection(part=part.number, table_ids=[], verdict="missing_data",
            missing=checks.SELECTION_FAILED_REASON) for part in plan.parts])
    return {"selection": selection, "selection_attempts": count, "selection_feedback": feedback}


def selected_tables(state: AnalystState, *, answerable_only: bool = True) -> list[CatalogEntry]:
    """Chosen tables in candidate order, deduplicated; only answerable parts feed code generation."""
    selection = state.get("selection")
    ids = {table_id for part in (selection.parts if selection is not None else [])
           if not answerable_only or part.verdict == "answerable" for table_id in part.table_ids}
    return [entry for entry in state.get("candidates", []) if entry.table_id in ids]


def generate_code(state: AnalystState, deps: AnalystDeps) -> dict[str, Any]:
    """One draft per attempt; malformed drafts are checked and retried without execution (D-121)."""
    plan, selection = state["plan"], state["selection"]
    assert plan is not None and selection is not None
    tables = selected_tables(state)
    history = state["attempts_history"]
    previous = PreviousAttempt(history[-1]["code"], history[-1]["feedback"]) if history else None
    try:
        draft = _invoke(CodeDraft, prompts.build_code_messages(plan, selection, tables, make_aliases(tables), previous), deps)
    except LLMProxyError:
        logger.debug("Code generation failed", exc_info=True)
        return _failure("llm")
    return {"code_draft": draft, "code_attempts": state["code_attempts"] + 1,
            "sandbox_result": None, "last_failure": None}


def valid_draft(state: AnalystState) -> bool:
    draft = state.get("code_draft")
    return draft is not None and bool(draft.code.strip()) and bool(draft.approach.strip())


def execute(state: AnalystState, deps: AnalystDeps) -> dict[str, Any]:
    """Prepare the prelude and only selected files, then call the isolated runner (FR-217)."""
    draft = state["code_draft"]
    assert draft is not None
    tables = selected_tables(state)
    script = prelude_source(make_aliases(tables)) + "\n" + draft.code
    try:
        folder = prepare_run_folder(script, {entry.table_id: deps.table_file(entry.table_id) for entry in tables},
                                    base_dir=deps.sandbox_base_dir)
        result = deps.sandbox_runner(folder, deps.settings.SANDBOX_TIMEOUT_SECONDS)
    except (SandboxError, TableStoreError):
        logger.debug("Calculation execution failed", exc_info=True)
        return _failure("sandbox")
    return {"sandbox_result": asdict(result)}


def attempt_check(state: AnalystState, deps: AnalystDeps) -> AttemptCheck:
    """Apply existing classification, including a failed draft that never reached the runner."""
    if not valid_draft(state):
        return AttemptCheck(failure="invalid_output", feedback=CODE_DRAFT_FEEDBACK)
    result, selection = state["sandbox_result"], state["selection"]
    assert result is not None and selection is not None
    return checks.classify_attempt(result["exit_code"], result["timed_out"], result["stdout"], result["stderr"],
        [part.part for part in selection.parts if part.verdict == "answerable"], deps.settings.SANDBOX_TIMEOUT_SECONDS)


def check(state: AnalystState, deps: AnalystDeps) -> dict[str, Any]:
    """Keep each complete attempt and its classification for the UI and next retry (FR-223)."""
    classified = attempt_check(state, deps)
    draft = state.get("code_draft")
    result = state.get("sandbox_result") or {"exit_code": 1, "timed_out": False, "stdout": "", "stderr": ""}
    attempt = {"code": draft.code if draft is not None else "", "approach": draft.approach if draft is not None else "",
               **result, "failure": classified.failure, "feedback": classified.feedback}
    return {"last_failure": classified.failure, "attempts_history": [*state["attempts_history"], attempt]}


def merge_status(state: AnalystState, deps: AnalystDeps) -> dict[str, Any]:
    """The final status is computed here, per part, never by the answer writer (FR-224/225)."""
    selection = state["selection"]
    assert selection is not None
    failed = state.get("last_failure") is not None
    emitted = attempt_check(state, deps).emitted if state.get("sandbox_result") is not None and not failed else []
    outcomes, status = checks.merge_status(selection, emitted, failed)
    return {"part_outcomes": outcomes, "answer_status": status}


def answer_facts(state: AnalystState) -> AnswerFacts:
    """Only permitted values/method and the related sources reach the answer writer (D-119)."""
    plan = state["plan"]
    assert plan is not None
    status = state["answer_status"]
    assert status is not None
    draft = state.get("code_draft")
    tables = selected_tables(state, answerable_only=False) or state.get("candidates", [])[:3]
    outcomes = [part.model_copy(update={"values": {}}) if status == "cannot_answer" or part.outcome != "answered" else part
                for part in state["part_outcomes"]]
    return AnswerFacts(plan.standalone_question, plan.parts, outcomes,
        draft.approach if draft is not None and status != "cannot_answer" else "",
        [TableSource(entry.name, entry.source_file, entry.pages) for entry in tables], status)


def respond(state: AnalystState, deps: AnalystDeps) -> dict[str, Any]:
    """Check answer numbers, retry once; absent answer routes to the deterministic template."""
    facts = answer_facts(state)
    previous, feedback = None, []
    for _ in range(NUMBER_RETRIES + 1):
        try:
            answer = _invoke(FinalAnswer, prompts.build_respond_messages(facts, previous=previous, feedback=feedback), deps)
        except LLMProxyError:
            logger.debug("Answer writing failed; using template", exc_info=True)
            return {"answer": None}
        if answer is None or not answer.text.strip():
            return {"answer": None}
        feedback = checks.check_numbers(answer.text, facts)
        if not feedback:
            return {"answer": answer.text}
        previous = answer.text
    return {"answer": None}


def template(state: AnalystState, deps: AnalystDeps) -> dict[str, Any]:
    return {"answer": checks.template_answer(answer_facts(state))}


def fail(state: AnalystState, deps: AnalystDeps) -> dict[str, Any]:
    """Infrastructure failure exit with the generic user message, never a backend name."""
    return {"answer_status": "cannot_answer", "answer": OUTAGE_MESSAGE, "part_outcomes": []}
