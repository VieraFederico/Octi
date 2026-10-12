# Iteration 1 — Table confirmation (human-in-the-loop bonus)

Commit SHA: (filled by student)
Commit summary: `Spec 03 · Iter 1: Add table confirmation before the Analyst calculates`

Started before spec 02 Iteration 4 was committed (student's call; its files were finished on disk).

## Criteria
| Criterion | Command | Result |
|---|---|---|
| Graph smoke tests first, seen failing | `.venv/bin/python -m pytest -q tests/unit/test_confirm_tables_graph.py` | FAIL as expected (`cannot import name 'resume_analysis'`) |
| UI smoke tests first, seen failing | `.venv/bin/python -m pytest -q tests/functional/test_confirm_tables.py` | FAIL as expected (no `ui.analysis.resume_analysis`) |
| Iteration tests + spec 02 flow | `.venv/bin/python -m pytest -q tests/functional/test_confirm_tables.py tests/functional/test_analysis_flow.py tests/unit/test_confirm_tables_graph.py` | PASS — 11 passed |
| Full offline suite | `.venv/bin/python -m pytest -q` | 1 failure not from this iteration: `tests/unit/test_readme.py::test_analyst_documentation_and_exported_graph_are_present` (spec 02 Iteration 5's README section not written yet) |

## Files
- Added: `tests/unit/test_confirm_tables_graph.py`, `tests/functional/test_confirm_tables.py`, this record.
- Changed: `agents/analyst/nodes.py` (`confirm_tables`, `confirmation_payload`, `apply_confirmation`,
  `CANCELLED_REASON`, `NO_TABLE_CHOSEN_REASON`), `agents/analyst/state.py` (`confirmation`),
  `agents/analyst/graph.py` (node, `route_after_confirm`, `CHECKPOINTER`, `run_analysis(..., confirm_tables,
  extra_tags=())`, `resume_analysis`, `abandon_analysis`, `confirmation` in end metadata),
  `ui/analysis.py` (toggle, pause, resume), `ui/chat.py` (toggle placement, composer disabled while
  paused), `specs/03-evaluation-plan-artifacts/DECISIONS.md` (S03-D-005).
- Spec 02 tests adapted (the plan asks for it): `tests/unit/test_analyst_graph.py`,
  `tests/unit/test_analyst_state.py`, `tests/unit/test_analyst_tracing.py` pass `confirm_tables=False`
  (the argument is required, D-112); `tests/analyst_stubs.py` `StubAnalysisRunner` accepts and records it.

## Deviations
- `extra_tags` added to `run_analysis` here (S03-D-004).
- New chat does not call `abandon_analysis` yet (S03-D-005).

## Deferred to the final iteration (D-118)
- VC-314 "no answerable part → no pause" and "off → no pause" as their own tests (the spec 02 route
  tests run with confirmation off); VC-315 unanswerable part's reason and non-candidate ids ignored;
  VC-316 part unticked → "No table was chosen."; all unticked → no code; VC-317 in the UI; VC-319
  New chat during a pause and sidebar enabled; VC-320 metadata values `confirmed` / `skipped`.
- NFR-304 layout (manual, student).

## For the next iteration
- Iteration 2b: `scripts/run_eval.py` calls `run_analysis(q, [], deps, False, extra_tags=("eval",))`.
