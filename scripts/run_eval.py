"""Run the evaluation: `python -m scripts.run_eval` (from the project root).

Uses the configuration it runs with (anyone's own `.env`):
1. syncs `eval/questions.yaml` into the LangSmith dataset `octi-eval`, one example per question id;
2. ingests each sample PDF whose document hash is not in the catalog (pauses answered automatically);
3. runs every question through the Analyst graph with table confirmation off, as one LangSmith
   experiment (`octi-eval-…`), each run tagged `eval`;
4. scores each run with the three deterministic evaluators and writes `eval/results.md`.

Exit codes: 0 when every question was run (whatever the marks); 1 when the evaluation could not
start (LangSmith, Pinecone or the proxy unreachable); 2 on invalid configuration.
"""

import subprocess
import sys
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agents.analyst.graph import mask_sandbox_output, run_analysis
from agents.analyst.state import make_deps as make_analyst_deps
from agents.ingestion.graph import build_graph as build_ingestion_graph
from agents.ingestion.graph import resume_ingestion, run_ingestion
from agents.ingestion.indexing import entry_from_record, load_catalog
from agents.ingestion.schemas import CatalogEntry
from agents.ingestion.pdf.tables import document_sha
from agents.ingestion.state import make_deps as make_ingestion_deps
from agents.ingestion.state import question_text
from eval.scoring import (
    EVALUATORS, Question, error_row, load_questions, score_run, status_correct, tables_correct,
    values_correct, write_results,
)
from scripts.make_sample_pdfs import ACME_FILE, INFORME_FILE, OUT_DIR
from services.errors import AppError, InvalidSettingsError
from services.settings import REPO_ROOT, Settings, get_settings
from services.tracing import make_langsmith_client, translate_tracing_errors

DATASET = "octi-eval"
EXPERIMENT_PREFIX = "octi-eval"
RUN_TAG = "eval"
QUESTIONS_FILE = REPO_ROOT / "eval" / "questions.yaml"
RESULTS_FILE = REPO_ROOT / "eval" / "results.md"
SAMPLE_FILES = (ACME_FILE, INFORME_FILE)
EVALUATOR_FUNCTIONS = dict(zip(EVALUATORS, (status_correct, values_correct, tables_correct), strict=True))
Out = Callable[[str], None]


def sync_dataset(client: Any, questions: list[Question], name: str = DATASET) -> Any:
    """Create or update the dataset: one example per question, matched by `id` in its metadata."""
    dataset = client.read_dataset(dataset_name=name) if client.has_dataset(dataset_name=name) else \
        client.create_dataset(name, description="Octi test questions (eval/questions.yaml).")
    existing = {(example.metadata or {}).get("id"): example for example in client.list_examples(dataset_id=dataset.id)}
    for question in questions:
        inputs = {"id": question.id, "question": question.question}
        outputs = question.model_dump(mode="json", exclude={"id", "question"})
        example = existing.get(question.id)
        if example is None:
            client.create_example(inputs=inputs, outputs=outputs, metadata={"id": question.id}, dataset_id=dataset.id)
        elif example.inputs != inputs or example.outputs != outputs:
            client.update_example(example.id, inputs=inputs, outputs=outputs, metadata={"id": question.id})
    return dataset


def ingest_samples(settings: Settings, catalog: list[CatalogEntry], out: Out = print,
                   folder: Path = OUT_DIR) -> list[CatalogEntry]:
    """Ingest each sample PDF not yet in the catalog (by document hash); returns the indexed entries.

    The entries come from the write acknowledgement, because a catalog read right after the write
    may not list them yet (the Index is eventually consistent).
    """
    known = {entry.document_sha for entry in catalog}
    deps, graph, indexed = None, None, []
    for name in SAMPLE_FILES:
        pdf = (folder / name).read_bytes()
        if document_sha(pdf) in known:
            out(f"{name}: already in the library")
            continue
        if deps is None:
            deps = make_ingestion_deps(settings)
            graph = build_ingestion_graph(deps)
        result = run_ingestion(graph, deps, name, pdf)
        while result.status == "paused":
            choices = result.question["choices"]
            choice = next((c for c in choices if c["value"] != "cancel"), choices[0])
            out(f"{name}: paused — {question_text(result.question)} → answered {choice['label']}")
            result = resume_ingestion(graph, deps, result.thread_id, choice["value"])
        out(f"{name}: {result.values['outcome']['status']}")
        if result.values["outcome"]["status"] == "indexed":
            indexed += [entry_from_record(item["record_metadata"]) for item in result.values.get("assembled") or []]
    return indexed


def commit_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              check=True, cwd=REPO_ROOT).stdout.strip() or "unknown"
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main(out: Out = print) -> int:
    try:
        settings = get_settings()
    except InvalidSettingsError as error:
        out("Invalid configuration: " + ", ".join(sorted(error.problems)))
        return 2
    questions = load_questions(QUESTIONS_FILE)
    by_id = {question.id: question for question in questions}
    try:
        with translate_tracing_errors():
            client = make_langsmith_client(settings, hide_inputs=mask_sandbox_output, hide_outputs=mask_sandbox_output)
            sync_dataset(client, questions)
        out(f"Dataset {DATASET}: {len(questions)} questions")
        catalog = load_catalog(settings)
        indexed = ingest_samples(settings, catalog, out)
        if indexed:
            fresh = {entry.table_id: entry for entry in load_catalog(settings)}
            catalog = list({**fresh, **{entry.table_id: entry for entry in indexed}}.values())
    except AppError as error:
        out(f"The evaluation could not start: {error.user_message}")
        return 1
    deps = replace(make_analyst_deps(settings, catalog=catalog), tracing_client=client)
    states: dict[str, dict] = {}
    errors: dict[str, str] = {}

    def target(inputs: dict) -> dict:
        question_id = inputs["id"]
        out(f"{question_id}: {inputs['question']}")
        try:
            state = run_analysis(inputs["question"], [], deps, False, extra_tags=(RUN_TAG,))
        except Exception as error:  # one failing question must not stop the others (FR-309)
            errors[question_id] = type(error).__name__
            return {"error": errors[question_id]}
        states[question_id] = state
        if state.get("error"):
            errors[question_id] = state["error"]["kind"]
        return {"answer_status": state.get("answer_status"), "answer": state.get("answer")}

    def evaluator(name: str) -> Callable[[Any, Any], dict]:
        def score(run: Any, example: Any) -> dict:
            question_id = example.metadata["id"]
            if question_id in errors or question_id not in states:
                return {"key": name, "score": 0, "comment": errors.get(question_id, "no run")}
            mark = EVALUATOR_FUNCTIONS[name](by_id[question_id], states[question_id])
            return {"key": name, "score": None if mark is None else int(mark),
                    "comment": "not applicable" if mark is None else ""}
        return score

    try:
        with translate_tracing_errors():
            results = client.evaluate(target, data=DATASET, evaluators=[evaluator(name) for name in EVALUATORS],
                                      experiment_prefix=EXPERIMENT_PREFIX, max_concurrency=0,
                                      metadata={"llm_model": settings.LLM_MODEL, "commit": commit_sha()})
    except AppError as error:
        out(f"The evaluation could not start: {error.user_message}")
        return 1
    traces: dict[str, str] = {}
    for row in results:
        try:
            traces[row["example"].metadata["id"]] = client.get_run_url(run=row["run"], project_name=results.experiment_name)
        except Exception:  # a missing link must not lose the results
            traces[row["example"].metadata["id"]] = ""
    rows = [error_row(q, errors[q.id], traces.get(q.id, "")) if q.id in errors or q.id not in states
            else score_run(q, states[q.id], traces.get(q.id, "")) for q in questions]
    header = {"Run date": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"), "Model": settings.LLM_MODEL,
              "Commit": commit_sha(), "Experiment": results.experiment_name}
    write_results(RESULTS_FILE, header, rows)
    out(f"Wrote {RESULTS_FILE.relative_to(REPO_ROOT)} ({len(rows)} questions)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
