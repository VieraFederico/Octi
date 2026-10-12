# Iteration 5 — Live checks and Analyst documentation

- **Commit SHA:** (filled by student)
- **Previous iteration:** `c894aba` (student committed during this session).
- **Scope:** live test definitions, final README, shared test helpers, final handoff.

## Shipped
- Live sandbox checks cover normal execution, inaccessible host canary, network isolation,
  timeout and process exhaustion. No actual secret file is touched; no image is pulled or built.
- Live ACME check ingests into an isolated namespace and temporary table store, runs the real
  Analyst with confirmation disabled, checks status/numeric evidence/table id, and cleans up.
- README describes the shipped chat, setup, configuration, calculation choices, trace behavior,
  limitations and the actual compiled graph (including the existing confirmation node).
- Analyst stubs moved into tests/stubs.py. Ingestion catalog_entry keeps its defaults;
  the Analyst helper is analyst_catalog_entry, aliased at existing import sites.

## Verification
- **RED:** `.venv/bin/python -m pytest -q tests/unit/test_readme.py` — 1 failed, 9 passed
  in 21.66 s before the README update; the missing Analyst documentation was detected.
- **WAIVED:** subsequent offline checks, regression and detailed deferred criteria: the student
  explicitly instructed "No time for tests, just do the code". No green result is claimed.
- **PENDING VC-242/243:** README/Dockerfile test rerun after documentation changes.
- **PENDING VC-244:** full suite, offline guards and under-60-second requirement.
- **PENDING VC-245:** student-run live checks with an existing local image and available SDK.
- **PENDING VC-247:** student timings, 1280/375 px layout and all three statuses in the real app.
- Compiled graph exported using existing WSL Python with fake settings, without service calls.
- Artifacts now describe implemented scope; final spec verification is **incomplete**.

## Exact files touched in this iteration
Created: `tests/live/test_sandbox_live.py`, `tests/live/test_analyst_live.py`, this record.

Changed:
- `README.md`, `tests/unit/test_readme.py`, `tests/stubs.py`, `tests/conftest.py`
- `tests/functional/conftest.py`, `tests/functional/test_analysis_flow.py`,
  `tests/functional/test_sandbox_startup.py`
- `tests/unit/test_analysis_ui.py`, `tests/unit/test_analyst_checks.py`,
  `tests/unit/test_analyst_graph.py`, `tests/unit/test_analyst_nodes.py`,
  `tests/unit/test_analyst_prompts.py`, `tests/unit/test_analyst_state.py`,
  `tests/unit/test_analyst_stubs.py`, `tests/unit/test_analyst_tracing.py`,
  `tests/unit/test_confirm_tables_graph.py`, `tests/unit/test_eval_scoring.py`,
  `tests/unit/test_prelude.py`, `tests/unit/test_sandbox.py`, `tests/unit/test_sandbox_health.py`
- `specs/02-analyst-plan-artifacts/CONTEXT.md`

Deleted: `tests/analyst_stubs.py`.
Concurrent app/graph/evaluation changes are excluded; imports in concurrent tests were migrated.

## Decisions and deviations
- No new product design decision. Builder renaming resolves a name collision mechanically.
- Secret-file read adapted to a synthetic host canary to obey the project's absolute secrets rule.
- The implementation subagent hit a usage limit; the root finished after the student's Continue.
- Existing S02-D decisions reflected in README: 001, 005–008, 010, 013–017, 019–021.
  Internal implementation details: 002–004, 009, 011–012, 018 (types, signatures, exact feedback,
  developer diagnostics and helper mappings); preserved in the decision log and source.
- Testing stopped on explicit student instruction. Live/manual checks remain student-owned.
- No installations, downloads, protected specification edits, commits or pushes by this agent.

## For the next iteration / evaluation
- Live: `.venv/bin/python -m pytest -m live` (student only; available SDK/daemon/local image).
- Offline: `.venv/bin/python -m pytest -q`; no additional verification was run in this iteration.
- Evaluation reads `answer_status`, `part_outcomes`, `attempts_history`, `error`.
- Trace root: `Analysis: <first 60 question characters>`, `analysis` tag; completion metadata
  records status, attempts and table ids. Sandbox text is masked from persisted traces.
- `confirm_tables` already follows `select`; run_analysis requires its boolean argument.
- Re-run documentation and shared-helper checks before claiming final spec acceptance.

Commit summary: `Spec 02 · Iter 5: Add live checks and document the Analyst agent`
