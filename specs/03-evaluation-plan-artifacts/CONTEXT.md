# CONTEXT — Spec 03 Evaluation, docs and bonus (after Iteration 2a)

Starting point: spec 00 complete; spec 01 committed through Iteration 6 (`0e10420`); spec 02
committed through Iteration 1 (`5a61b7e`), its Iteration 3 (graph) in progress in another tab.
Order changed by S03-D-001: 2a (questions + scoring, done) → 1 (table confirmation, after spec 02
Iteration 4) → 2b (`scripts/run_eval.py`, after spec 02 Iteration 3) → 3 (live run and docs).
Staged verification (D-118) applies.

## Current state
- `eval/questions.yaml`: the 10 test questions of FR-302, one per category; expected values
  recomputed from `scripts/make_sample_pdfs.py`'s constants by a test (BR-301).
- `eval/scoring.py`: YAML schema and loader, the three deterministic evaluators, result rows and the
  `eval/results.md` writer.
- Not yet: `confirm_tables` node, pause UI and toggle (Iteration 1); `scripts/run_eval.py`, the
  LangSmith dataset sync and the experiment (Iteration 2b); `EVALUATION.md`, README (Iteration 3).

## File map
- `eval/__init__.py` — package marker.
- `eval/questions.yaml` — the test questions (FR-301 … FR-303).
- `eval/scoring.py` — `Question`, `ExpectedValue`, `load_questions`, evaluators, `ResultRow`,
  `score_run`, `error_row`, `totals`, `write_results`.
- `tests/unit/test_eval_questions.py` — schema, coverage, values vs constants (smoke).
- `tests/unit/test_eval_scoring.py` — evaluators on fake states, results file (smoke).
- `requirements.txt` — + `PyYAML==6.0.3` (S03-D-002).

## Public interfaces
- `load_questions(path) -> list[Question]` (raises on malformed YAML or a repeated id) → `eval/scoring.py`.
- `Question(id, question, category, expected_status, expected_values: list[ExpectedValue],
  expected_tables, expected_answer)`; `ExpectedValue(name, value, unit: "percent" | None)`;
  `CATEGORIES` (the 10 FR-302 categories) → `eval/scoring.py`.
- Evaluators `(question, state) ->`: `status_correct` → bool; `values_correct` → bool or `None`
  (`cannot_answer`); `tables_correct` → bool; helper `selected_table_names(state)` → `eval/scoring.py`.
- `score_run(question, state, trace_url="") -> ResultRow`; `error_row(question, error_kind,
  trace_url="") -> ResultRow`; `totals(rows) -> {evaluator: (passed, applicable)}`;
  `write_results(path, header: Mapping[str, str], rows)` → `eval/scoring.py`.

## Conventions & invariants
- The final state is a mapping read through spec 02 §7's field names: `answer_status`,
  `part_outcomes` (`PartOutcome`), `selection` (`TableSelection`), `candidates` (`CatalogEntry`),
  `code_attempts`. Missing fields read as empty.
- Selected tables for scoring = the table ids of parts with verdict `answerable`, mapped to names
  through `candidates` (D-112).
- Tolerance: 1 % relative, 0.001 absolute for an expected 0; `unit: percent` matches `v` or `v/100`.
  Only numeric (non-bool) values of `answered` outcomes are compared.
- Retries = `code_attempts − 1` (never below 0); an error row shows "–" retries and three ✗.
- `eval/results.md` layout: `# Evaluation results`, header bullets `- Name: value`, the table with
  columns `id | Question | Expected | Actual | Status | Values | Tables | Retries | Trace`, then
  `## Totals` with `- <evaluator>: passed/applicable` (+ "(N not applicable)"). Written with LF.
- Developer-facing files may name LangSmith (BR-307); the app UI never does.

## Commands
```bash
.venv/bin/python -m pytest -q tests/unit/test_eval_questions.py tests/unit/test_eval_scoring.py
.venv/bin/python -m pytest -q    # full offline suite
```
On this Windows machine the venv is a WSL one: `wsl.exe --cd "<repo as /mnt/c/...>" -- .venv/bin/python -m pytest -q`.

## Known gaps
- `expected_tables` hold provisional names taken from the PDF captions (S03-D-003): the real Table
  names come from the ingestion LLM and must be checked after ingesting the sample PDFs.
- VC-301 … VC-303, VC-308 … VC-310 are smoke-tested only; the full per-VC tests (including a
  deliberately wrong YAML copy failing VC-303) are deferred to Iteration 3 (D-118).
- `scripts/run_eval.py` (FR-304 … FR-307, FR-309 wiring, FR-311) does not exist yet.
