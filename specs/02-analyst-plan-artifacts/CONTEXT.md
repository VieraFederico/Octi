# CONTEXT — Spec 02 Analyst (after Iteration 5)

Spec 02 v0.9 (D-120/D-121), staged verification (D-118). Iteration 3 is committed in
`236b2cf`; spec 01's Iteration 7 record is committed. Iteration 4 was implemented alone.
Iteration 5 adds live checks, final README documentation and shared stubs. Verification remains incomplete: further testing was waived by the student for submission.

## Current state
- Pure pieces: §7 models, four prompts, answerability rules, selection/attempt/number checks,
  per-part status merge, template answer, aliases and trusted prelude.
- Sandbox: copied script/selected Parquet files, 0755/0644 permissions, exact isolation flags,
  timeout kill, output tails capped at 64 KB, cleanup, startup check and developer setup screen.
- Graph: catalog reload/empty route; four-turn planning; ranked phrase retrieval; selection retry;
  draft/execution retries including malformed drafts; history; merge; checked response/template;
  generic fail exit. State contains all node-to-node values, no catalog or DataFrame.
- Tracing: documented Client masking across every payload; explicit root start/end labels and
  execute metrics. Actual UI output remains available; raw output is excluded from persisted traces.
- Chat now runs analysis. A durable message streams progress, then shows the badge, answer,
  missing parts and folded tables/code/output/attempts. Selection-only runs show Tables considered;
  service failures show the generic error box. Full tables load only when Show data opens.
- PDF questions run after ingestion finishes, including cancelled/failed runs. The chat-side
  handoff preserves spec 01's source files and clears its legacy placeholder seam.
- Composer/sidebar controls disable for Analysis. History-derived memory contains only the last
  four completed Analysis question/answer pairs; New chat clears it with the message history.

## File map
- `agents/analyst/schemas.py` — Pydantic models and plain Turn/PreviousAttempt/AttemptCheck/facts.
- `agents/analyst/prompts.py` — four prompts, shared rules, few-shots, message builders and caps.
- `agents/analyst/checks.py` — selection validation, attempt classification, merge, numbers, template.
- `agents/analyst/prelude.py` — aliases and trusted table-loading/emit source.
- `agents/analyst/state.py` — graph state, attempt/error shapes, dependencies and production factory.
- `agents/analyst/nodes.py`, `graph.py` — nodes, routing, streaming, masking and tracing.
- `services/sandbox.py`, `sandbox/Dockerfile` — agent-agnostic execution and image recipe.
- `services/vector_store.py` — agent-agnostic query helper and existing ingestion operations.
- `services/tracing.py` — client factory with optional input/output masking hooks.
- `ui/analysis.py` — queued/running/finished message, progress, evidence and lazy table loading.
- `ui/analysis_window.py` — pure memory builder.
- `ui/chat.py`, `app.py`, `ui/sidebar.py` — Analysis submission/handoff/rendering/busy controls.
- `tests/stubs.py` — Analyst builders, fake Docker, extended model/embedding/query fakes,
  sandbox runner, trace recording transport and UI runner/result fixtures.
- `tests/unit/test_analyst_*.py`, `test_prelude.py`, `test_sandbox*.py` — graph/pure/service smoke and
  earlier function tests. `test_analysis_ui.py`, `test_analysis_window.py` — UI state/window smoke.
- `tests/functional/test_analysis_flow.py` — streaming/history/lazy data, PDF endings and layouts.
- Existing chat/app/ingestion functional tests now expect Analysis instead of the superseded placeholder.
- Artifacts: decisions append-only; records 01–05. README and live test definitions are present; exhaustive/live/manual verification remains pending.

## Public interfaces
- Models: QueryPlan/QuestionPart, TableSelection/PartSelection, CodeDraft, EmittedPart,
  PartOutcome, FinalAnswer → schemas.py. Field descriptions carry count/conditional rules;
  plain code enforces them (S02-D-001).
- Message builders: build_understand_messages(question, window),
  build_select_messages(plan, candidates, previous=None, feedback=()),
  build_code_messages(plan, selection, selected, aliases, previous=None),
  build_respond_messages(facts, previous=None, feedback=()) → prompts.py.
  Respond retry `previous` is text. Only answered values and a permitted method reach its facts.
- Checks: check_selection, classify_attempt(..., timeout_seconds), merge_status,
  check_numbers (feedback sentences), template_answer → checks.py.
- Prelude: make_aliases(selected) returns alias → table_id; prelude_source(aliases) loads /work files.
- Sandbox: prepare_run_folder(script, table_files, *, base_dir=None) → owned Path;
  run_script(folder, timeout_s, client=None) → frozen SandboxResult(exit_code, timed_out, stdout, stderr);
  check_docker(client=None) → DockerStatus(ok/unreachable/image_missing). FALLBACK_RUN_DIR points
  to ignored data/sandbox_runs/. Injected clients remain caller-owned; internally built clients close.
- AnalystState → state.py: spec v0.9 fields, including code_draft, selection_feedback, sandbox_result
  (plain dict). Attempts also carry approach, timeout and feedback. No settings/clients/files/frames.
- make_deps(settings, *, catalog=None) → AnalystDeps; None means not loaded, [] means loaded/empty.
  All service/model/table-path/runner seams are injected lazily; sandbox_base_dir can be overridden.
- build_graph(deps), run_analysis(question, window, deps, confirm_tables, *, on_update=None, thread_id=None, extra_tags=())
  → graph.py. Returns final state; callback receives (node_name, partial_update).
- run_config, end_metadata, execution_metrics, mask_sandbox_output, tracing_scope → graph.py.
  Root is Analysis: <first 60 question chars>; compiled graph child is Analyst graph.
- selected_tables(state, *, answerable_only=True), answer_facts(state) → nodes.py.
- query_records(index, namespace, vector, top_k) → services/vector_store.py: id/score/metadata.
- make_langsmith_client(settings, *, hide_inputs=None, hide_outputs=None) → services/tracing.py.
- UI: new_message(question), queue_analysis(state, question), is_busy(state),
  status_line(node, values, max_retries), render_analysis_message(message) → ui/analysis.py.
- Message fields: role/content/kind=analysis/question/thread_id/status/lines/values. Session key
  active-analysis points to the queued/running message and is removed on completion.
- build_window(messages) → list[Turn] (last four finished Analysis messages) → analysis_window.py.
- queue_finished_upload_question(state) → chat.py; called before sidebar rendering in app.py.
  It waits for ingestion/modals to finish and queues exactly once after the latest PDF user turn.
  Spec 01's imported QUESTION_PLACEHOLDER remains an empty compatibility constant.
- Show data widget key: analysis-data-<thread_id>-<table_id>; stateful expander with rerun.
  _full_table caches frames outside messages/state, by thread/table. No read before expansion.
- Real spec 01 seams: CatalogEntry/load_catalog/entry_from_record, ui.catalog session keys
  catalog/catalog-loaded/ingestion-settings, render_table_card, Parquet store paths.
- Test helpers and their scripting are defined in tests/stubs.py, including StubAnalysisRunner and analyst_catalog_entry (ingestion catalog_entry remains unchanged).

## Conventions & invariants
- No secret-file reads, installs/downloads, commits/pushes or protected root/spec edits.
- Spec-local choices use S02-D-NNN. Spec 01 source/artifact ownership is preserved.
- Services remain agent-agnostic. All model/embedding calls use the configured university proxy.
- Status is computed by code; answer prose cannot change it. Backend names/raw outages never
  appear in chat. Developer startup diagnostics may name services.
- Code attempts are bounded by ANALYST_MAX_RETRIES+1; malformed drafts skip execution, still
  consume an attempt and get D-121's feedback. Only the last attempt feeds a code retry.
- Stdout/stderr retain the last 65,536 bytes. Generated code executes only in the sandbox.
- History records completed attempts. Tracing masks output and copied retry feedback everywhere;
  injected tracing clients must use the same documented masking hooks.
- UI history contains metadata and capped evidence, never full frames or Settings.
- LF, neutral English, offline Given/When/Then tests. Detailed VCs are consolidated in Iteration 5.

## Commands
Run via existing WSL venv from PowerShell:
`wsl.exe --cd "<repo as /mnt/c/...>" -- .venv/bin/python -m pytest -q`

UI smoke:
`.venv/bin/python -m pytest -q tests/unit/test_analysis_window.py tests/unit/test_analysis_ui.py tests/functional/test_analysis_flow.py`
— 10 passed in 25.35 s.

Graph smoke:
`.venv/bin/python -m pytest -q tests/unit/test_analyst_graph.py tests/unit/test_analyst_nodes.py tests/unit/test_analyst_state.py tests/unit/test_analyst_tracing.py`
— 29 passed after Iteration 3. Full suite after Iteration 5: 734 passed, 2 live tests deselected in 62.99 s.

## Known gaps
- Detailed deferred VCs remain pending; the student waived further tests to meet the submission deadline.
- Last observed WSL venv lacks docker==7.1.0. Fakes work; production needs the existing pinned SDK
  available and the student-built image. No dependency/image operation was run by this agent.
- README sandbox setup and Analysis documentation are complete.
- Real isolation/services, output masking in live traces, 375/1280 px layout and timings are student checks.
- The current graph includes spec 03 table confirmation and checkpointing. run_analysis requires confirm_tables; live tests explicitly disable it.
- Template fallback is English; model response uses the question's language.
- A very long question can exceed the select prompt budget; a wrong row can produce plausible output.
- AppTest opens Show data through widget state; browser interaction remains manual verification.
- Compatibility placeholder imports in untouched spec 01 files can be removed in a separately
  authorized cleanup; they display no placeholder and do not prevent Analysis handoff.
