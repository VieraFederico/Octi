# Iteration 05 — The ingestion graph + Pauses and tracing

Commit SHA: (filled by student). Previous commit (Iteration 4): `2d3fb4d`.
Spec version read before implementation: **1.0**.
Mode: parallel (D-115). Lead (contract, briefs, integration): Claude Opus. Packages WP-A (nodes),
WP-B (wiring and tracing), WP-C (graph tests): Grok 4.7 High Fast subagents, briefs written by the
lead. Staged verification (D-118) applied from mid-iteration: code complete, smoke tests for code
written after it, remaining VC-by-VC tests deferred (list below).

## Criteria
Iteration command: `.venv/bin/python -m pytest -q tests/unit/test_state.py tests/unit/test_nodes.py tests/unit/test_graph.py tests/unit/test_graph_routing.py tests/unit/test_tracing_config.py` → 94 passed.

| Criterion | Test (file) | Result |
|---|---|---|
| VC-105, VC-106, VC-107 (node part): sentence in `outcome`, zero LLM / embedding / index calls, store empty | `test_nodes.py` | PASS |
| VC-130: model `LLM_MODEL` with another picker model; structured output `(TableEnrichment, include_raw)` | `test_nodes.py` | PASS |
| VC-134, VC-135, VC-136 | `test_graph.py` | PASS |
| VC-144 (node part): 400 long descriptions → `table` Skipped part, nothing assembled | `test_nodes.py` | PASS |
| VC-145, VC-147 | `test_graph.py` | PASS (both FR-142 sentences; same ids twice) |
| VC-146: 6 Tables, every retry, R = 2 → no recursion error; a too-small limit raises | `test_graph_routing.py` | PASS (fake nodes) |
| VC-159: messages + final state (`test_graph.py`); run config (`test_tracing_config.py`) | both | PASS |
| VC-160: skipped Table's feedback only in DEBUG log | `test_nodes.py` | PASS |
| VC-167 (node part): 200 rows → no bytes / DataFrame in updates, `rows` ≤ 20 | `test_nodes.py` | PASS |
| VC-168 (node part): proxy failure → FR-160 sentence, no service name, no Skipped part | `test_nodes.py` | PASS |
| VC-123 (pause part), VC-124, VC-137 | `test_graph.py` | PASS |
| VC-156: run name, tag, six metadata keys, `run_id`; resume keeps `thread_id` | `test_tracing_config.py` | PASS |
| VC-157: tracing on, no `LANGSMITH_*` env → active context for `LANGSMITH_PROJECT` (stub client) | `test_tracing_config.py` | PASS |
| Per-run store: open / get / close, document closed, empty after the run | `test_state.py`, `test_graph.py` | PASS |
| Full suite | `.venv/bin/python -m pytest -q` | 646 passed, 1 failed, 1 deselected (41.9 s). The failure is `tests/unit/test_analyst_prompts.py::test_respond_messages_for_cannot_answer_hold_no_value`, spec 02 work in progress in another tab; no spec 01 test fails |
| Artifacts | read-only inspection | PASS: CONTEXT updated, S01-D-021 … 023, this record |

## Deferred to the final iteration (D-118)
- VC-105, VC-106, VC-107 (graph part: FR-108 through `run_ingestion`, fake Pinecone and store unchanged)
- VC-144 (graph part: the too-large Table listed in the `ask_skipped` pause; Index N indexes the others)
- VC-167 (checkpoint part: every checkpointed state holds ≤ 20 rows and no bytes)
- VC-168 (graph part: the run ends without a pause, nothing written or deleted)

## TDD evidence
- Lead: `test_state.py` first → `ModuleNotFoundError: agents.ingestion.state`; then 5/5.
- WP-A: `test_nodes.py` first → `NotImplementedError`; then 31/31.
- WP-B: routing and tracing tests first → `NotImplementedError`; then 43/43.
- WP-C: 15 tests red with `NotImplementedError` in `build_graph` only; green after integration.

## Files
Added: `agents/ingestion/state.py`, `agents/ingestion/nodes.py`, `agents/ingestion/graph.py`,
`tests/unit/test_state.py`, `tests/unit/test_nodes.py`, `tests/unit/test_graph.py`,
`tests/unit/test_graph_routing.py`, `tests/unit/test_tracing_config.py`, this record.
Changed: `tests/stubs.py` (+ `ScriptedChatModel`, `enrichment_for`, `invalid_enrichment`),
`specs/01-ingestion-plan-artifacts/CONTEXT.md`, `…/DECISIONS.md` (S01-D-016, 018, 019, 020 marked
accepted; S01-D-021 … 023 added).
Deleted: none.

## Decisions
S01-D-021 (wording), S01-D-022 (deps and per-run store), S01-D-023 (recursion limit from a pre-count).
All three were chosen by the student in chat.

## Deviations
- No "Table store root" in the deps (S01-D-022): `TABLE_STORE_DIR` plus the `table_store_dir` fixture.
- The FR-143 limit uses an upper bound of T counted before the run (S01-D-023).
- `tracing_scope` builds the client with `make_langsmith_client` only when tracing is on and no client
  is passed (that client contacts LangSmith on creation; offline tests always pass a stub).

## Gotchas
- `langsmith.Client(...)` starts a background thread that calls `GET /info` immediately.
- Calling `interrupt` outside a graph fails: node tests patch `agents.ingestion.nodes.interrupt`.
- "Previous answer" / "Feedback to fix" also appear in the system prompt: check the last message only.
- Run the WSL venv from PowerShell as `wsl .venv/bin/python -m pytest …` (cwd is inherited).

## For the next iteration
- Iteration 6 keeps `graph` and `deps` together in the session (the checkpointer and the per-run
  store live there): `deps = make_deps(settings)`, `graph = build_graph(deps)`.
- Status lines: `on_update(node, update)` per node; pause buttons from `question["choices"]`; escape
  the bullets (captions are PDF text). Cards from `entry_from_record(item["record_metadata"])`.
- New chat at a pause: `deps.runs.close(thread_id)` (FR-162).
- Suggested message: `Spec 01 · Iter 5: Build the ingestion graph with the validation loop, pauses and LangSmith run labels`.
