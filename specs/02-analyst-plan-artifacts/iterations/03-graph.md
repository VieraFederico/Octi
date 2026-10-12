# Iteration 3 — The Analyst graph

- **Commit SHA:** (filled by student)
- **Previous iteration:** `c17cb59` — Docker sandbox and startup checks.
- **Mode:** one agent; staged verification (D-118); Spec 02 v0.9 (D-120/D-121).

## Implemented scope
- Explicit state, lazy injected dependencies, all graph nodes/conditional edges and streaming API.
- Catalog reload/empty library; four-turn planning; ranked multi-query retrieval; selection retry;
  prelude/file preparation; bounded calculation retries including malformed drafts; attempt history;
  per-part merge; number-checked response/template; generic infrastructure failure exit.
- Public Client masking on every span, execution metrics, root start/end metadata (A-204).

## Verification
Commands use the existing WSL venv from the repo root, with offline guards.
- **RED:** the smoke command below produced four collection errors before graph modules existed.
- **PASS:** `.venv/bin/python -m pytest -q tests/unit/test_analyst_graph.py tests/unit/test_analyst_nodes.py tests/unit/test_analyst_state.py tests/unit/test_analyst_tracing.py`
  — 29 passed in 4.33 s. Scripted models, fake retrieval, stub runner and recording SDK transport.
- **PASS:** `.venv/bin/python -m pytest -q` — 724 passed, 2 live tests deselected in 62.40 s.
- **Whitespace:** `git diff --check -- <iteration-owned tracked files>` passed.

## Graph routes exercised
- Answered/partial; empty library; catalog reload success/failure; select → retry/success;
  select → missing after exhausted retry; selection with no answerable part → merge.
- Calculation → success/missing; failed calculation → retry/exhaustion; malformed draft → check
  without execute → retry/exhaustion; final answer → valid/retry/template; malformed/outage answer
  → template; understand/select/generate/retrieve/execute outage → fail; malformed/empty plan → fail.
- Node smoke: ranked phrase merge/cap; unanswered facts omit method/values. State smoke: independent
  runs. Trace smoke: actual SDK masking and completion metadata, plus no client when tracing is off.

## Deferred to the final iteration (D-118)
- Individual exhaustive checks: VC-202, VC-248, VC-203 (window), VC-204, VC-206 (state), VC-207,
  VC-208, VC-209, VC-211, VC-212, VC-213 (graph), VC-215 (prelude seam), VC-219, VC-220, VC-221,
  VC-222 (graph), VC-224, VC-225, VC-226 (graph), VC-227, VC-228, VC-236, VC-237, VC-239, VC-240.
- Smoke routes exercise these contracts together; no per-VC completion gate is used here.
- Live service/image/isolation and timing checks remain student-run in Iteration 5.
- NFR-203's 60-second suite target remains final verification; this combined suite took 62.40 s.

## Files
- **Created:** `agents/analyst/state.py`, `agents/analyst/nodes.py`, `agents/analyst/graph.py`,
  `tests/unit/test_analyst_graph.py`, `tests/unit/test_analyst_nodes.py`,
  `tests/unit/test_analyst_state.py`, `tests/unit/test_analyst_tracing.py`, this record.
- **Changed:** `services/vector_store.py`, `services/tracing.py`, `tests/analyst_stubs.py`,
  `specs/02-analyst-plan-artifacts/CONTEXT.md`, `specs/02-analyst-plan-artifacts/DECISIONS.md`.
- **Deleted:** none. Concurrent spec tab/spec 01 changes are excluded.

## Decisions and deviations
- S02-D-015/016: student-revised explicit state (D-120), final-state/callback API, lazy dependencies.
- S02-D-017: student-selected documented Client masking and public root metadata update, no tracer
  subclass. The factory accepts optional hooks; original callers remain compatible.
- S02-D-018: real spec 01 interfaces and Analyst-local extensions of its fakes; approved query helper.
- S02-D-019: malformed-output handling (D-121); invalid drafts consume a retry without a container.
- The first implementation run exposed an answer retry argument mismatch (object instead of text)
  and a test file-order assumption; both corrected before the passing smoke run.

## For the next iteration
- `make_deps(settings, catalog=session_catalog if loaded else None)` creates dependencies without
  service calls. `run_analysis(question, window, deps, on_update=...)` returns final state.
- Callback updates contain the node's partial state. `code_draft`, `sandbox_result` and
  `attempts_history` supply evidence; candidates/selection determine used/considered tables.
- Answer is a string; status/outcomes are computed state; `error` is None or kind + generic message.
- Window contains only `Turn(question, answer)` for the last four Analysis turns; UI builds it.
- For shared-files review, include only this record's files. Nothing committed/pushed/installed;
  no live model, daemon, image build/pull or generated script execution used during verification.
- Stop here for review/commit. Iteration 4 requires spec 01 Iteration 7 committed.

Commit summary: `Feat: Analyst Graph and Self-Correction (Spec 2)`
