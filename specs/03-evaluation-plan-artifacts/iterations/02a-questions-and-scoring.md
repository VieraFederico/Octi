# Iteration 2a — Test questions and scoring

Commit SHA: (filled by student)
Commit summary: `Spec 03 · Iter 2a: Add the test questions and their deterministic scoring`

Scope (S03-D-001): the parts of plan Iteration 2 that need no unbuilt code — `eval/questions.yaml`,
`eval/scoring.py` and their smoke tests. Staged verification (D-118).

## Criteria
| Criterion | Command | Result |
|---|---|---|
| Smoke tests written first and seen failing | `.venv/bin/python -m pytest -q tests/unit/test_eval_questions.py tests/unit/test_eval_scoring.py` | FAIL as expected (`No module named 'eval'`) |
| Smoke tests pass | same command | PASS — 4 passed |
| Full offline suite | `.venv/bin/python -m pytest -q` | PASS — 724 passed, 2 deselected, 60.6 s (other tabs' runs in parallel) |

## Files
- Added: `eval/__init__.py`, `eval/questions.yaml`, `eval/scoring.py`,
  `tests/unit/test_eval_questions.py`, `tests/unit/test_eval_scoring.py`,
  `specs/03-evaluation-plan-artifacts/CONTEXT.md`, `specs/03-evaluation-plan-artifacts/DECISIONS.md`,
  this record.
- Changed: `requirements.txt` (+ `PyYAML==6.0.3`, S03-D-002).
- No existing spec 01 / 02 test changed.

## Deviations
- Iteration order (S03-D-001): `scripts/run_eval.py` and the fake LangSmith client are not in this
  iteration; they come in Iteration 2b, after spec 02 Iteration 3 is committed.
- `expected_tables` names are provisional (S03-D-003).

## Spec problems for the spec tab
- A-302 says spec 01's `CONTEXT.md` lists the extracted Table names; it lists only table numbers
  and pages. Table names are LLM output, so FR-308's name matching depends on a live ingestion.
  Options: (a) the student copies the real names after ingesting (current plan); (b) match
  `expected_tables` by caption/number through the Index record's `table_id` page and position;
  (c) match names case-insensitively by containment. Recommendation: (a), with (c) if names drift.
- FR-302 (9) "no national row": the regional *net sales* do sum to the national net revenue, so q09
  uses market share (not additive) as the missing comparison.

## Deferred to the final iteration (D-118)
- VC-301 full (each field missing, wrong type, repeated id, bad category rejected).
- VC-302 full (the expected status of each category asserted one by one).
- VC-303 second half: a deliberately wrong value in a copy of the YAML makes the test fail.
- VC-308 full: inside/outside 1 % at both edges, expected 0 matched by 0.0005, percent edge cases,
  non-numeric values ignored, missing `selection`.
- VC-309 / VC-310 full: ten rows, every column checked, "N not applicable" totals.
- VC-304 … VC-307, VC-311, VC-312: belong to Iteration 2b.

## Gotchas
- The final state is read as a mapping with spec 02 §7 field names; rows tolerate missing fields.
- `values_correct` compares only numeric, non-bool values of `answered` outcomes.

## For the next iteration
- Iteration 1 needs spec 02's `agents/analyst/graph.py`, `nodes.py`, `state.py` and `ui/analysis.py`.
- Iteration 2b: `scripts/run_eval.py` calls `load_questions`, `score_run` / `error_row` and
  `write_results`; LangSmith evaluators wrap the three functions (`None` → no score).
- Before the live run: ingest the sample PDFs, read the real Table names, update `expected_tables`.
