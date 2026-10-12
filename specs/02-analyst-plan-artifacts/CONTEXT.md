# CONTEXT — Spec 02 Analyst agent (after Iteration 2)

Starting point: spec 00 complete; spec 02 Iteration 1 committed (`5a61b7e`). Spec 01's committed
records currently reach Iteration 5, and its next UI iteration is being implemented concurrently;
read its current artifacts before consuming its interfaces. Iteration 2 was implemented alone.
Spec 02 v0.7 and staged verification (D-118) apply. Iteration 4 requires spec 01 Iteration 7 committed.

## Current state
- `Settings.ANALYST_MAX_RETRIES` (int 0–5, default 2) and `Settings.SANDBOX_TIMEOUT_SECONDS` (int
  5–120, default 30) parsed and documented in `.env.example` (FR-241).
- Error tree: `SandboxError` (`service = "Docker"`) with leaf `SandboxUnavailableError`.
- `agents/analyst/schemas.py`: every SPEC §7 model plus the plain shapes of S02-D-002.
- `agents/analyst/prompts.py`: the four prompts v1 (Class 4), `RULES_BLOCK` verbatim, the three
  few-shot pairs (`SELECT_EXAMPLES`, `CODE_EXAMPLE`), `candidate_block` with the FR-209 caps, the four
  message builders. Measured: 10 maximum-size candidates → largest block 3,495, prompt 39,552 chars.
- `agents/analyst/checks.py`: selection check, attempt classification, status merge, number check,
  template answer.
- `agents/analyst/prelude.py`: alias rule and the prelude source with `emit`'s safety net.
- `tests/analyst_stubs.py`: `catalog_entry(...)`, `query_plan(...)`, `FakeDockerClient`.
- `tests/unit/test_analyst_pieces.py`: seam tests — the code few-shot runs through the prelude and
  every check; its aliases are the ones `make_aliases` derives.
- `services/sandbox.py`: isolated execution, temporary folders, bounded output tails, timeout kill,
  cleanup, lazy SDK factory, safe error translation and read-only daemon/image checks.
- `sandbox/Dockerfile`: `python:3.13-slim`, pandas 3.0.6, pyarrow 25.0.1, non-root user 10001.
- Startup requires a healthy sandbox as well as valid settings and index; developer setup errors
  name Docker and the image build command. Diagnostics include a `docker` line.
- Not yet: the graph (3), the Analysis UI (4), exhaustive VC tests, live checks and README (5).

## File map
- `agents/analyst/__init__.py` — package marker.
- `agents/analyst/schemas.py` — SPEC §7 models and plain data shapes.
- `agents/analyst/prompts.py` — rules block, the four prompts, few-shots, message builders.
- `agents/analyst/checks.py` — plain-code decisions (selection, attempts, merge, numbers, template).
- `agents/analyst/prelude.py` — prelude source and alias naming.
- `services/settings.py`, `services/errors.py`, `.env.example` — shared with spec 01 (D-105).
- `tests/analyst_stubs.py` — Analyst test builders (moved into `tests/stubs.py` in Iteration 5).
- `tests/unit/test_analyst_stubs.py` — the builders build valid models.
- `tests/unit/test_analyst_prompts.py` (37), `tests/unit/test_analyst_checks.py` (70),
  `tests/unit/test_prelude.py` (4), `tests/unit/test_analyst_pieces.py` (2) — the package tests and
  the seams.
- `tests/unit/test_settings.py`, `tests/unit/test_errors.py` — + VC-238 cases.
- `services/sandbox.py`, `sandbox/Dockerfile` — sandbox service and student-built image recipe.
- `ui/startup.py`, `ui/error_screen.py`, `services/health.py`, `scripts/check_services.py` — shared
  startup/diagnostic integration (student-approved).
- `tests/conftest.py` — approved offline fake-Docker factory; live tests retain real factories.
- `tests/unit/test_sandbox.py`, `tests/unit/test_sandbox_health.py`,
  `tests/functional/test_sandbox_startup.py` — six smoke cases across execution and integration.
- `tests/unit/test_check_services.py`, `tests/unit/test_error_screen.py` — existing expectations
  updated for the added service; `.gitignore` excludes `data/sandbox_runs/`.

## Pure-piece contract (Iteration 1; historical package ownership)

### Ownership (nobody edits another package's files)
| Package | Owns | VCs |
|---|---|---|
| Lead | `services/settings.py`, `services/errors.py`, `.env.example`, `agents/analyst/__init__.py`, `agents/analyst/schemas.py`, `RULES_BLOCK` and `LATEST_MESSAGE_WINS` in `prompts.py`, `tests/analyst_stubs.py`, `tests/unit/test_analyst_stubs.py`, the artifacts | VC-238 |
| WP-A prompts | `agents/analyst/prompts.py` (all but the two verbatim constants and the caps), `tests/unit/test_analyst_prompts.py` | VC-205, VC-209 (input part), VC-210, VC-213 (prompt part), VC-214, VC-224 (prompt part), VC-225 (prompt part), VC-241, VC-246 |
| WP-B checks | `agents/analyst/checks.py`, `tests/unit/test_analyst_checks.py` | VC-211 (check part), VC-219 (classification), VC-222 (merge part), VC-225 (template), VC-226 (function part) |
| WP-C prelude | `agents/analyst/prelude.py`, `tests/unit/test_prelude.py` | VC-223 |

Signatures are fixed as written in the modules; read each docstring. Constants already in the
modules keep their names and values.

### Shared data (`agents/analyst/schemas.py`, final)
- Literals: `Verdict`, `EmitStatus`, `Outcome`, `AnswerStatus`, `FailureKind` =
  `python_error | timeout | invalid_output | wrong_parts`; `Value = float | int | str`.
- SPEC §7 models: `QuestionPart`, `QueryPlan`, `PartSelection`, `TableSelection`, `CodeDraft`,
  `EmittedPart`, `PartOutcome`, `FinalAnswer`. No count or conditional validators (S02-D-001).
- `Turn(question, answer)`; `PreviousAttempt(code, feedback)`;
  `AttemptCheck(failure, feedback="", emitted=[])`; `TableSource(name, source_file, pages)`;
  `AnswerFacts(question, parts, outcomes, approach, tables, answer_status)`.
- Candidate and Selected tables are spec 01's `CatalogEntry` (`agents/ingestion/schemas.py`):
  `table_id`, `name`, `description`, `columns` (`ColumnMetadata`: `name`, `description`, `unit`,
  `dtype`), `row_headers` (≤ 50), `row_headers_total`, `source_file`, `pages`, `preview` (column
  names line, then up to 5 `a | b` rows), `n_rows`, `n_cols`.

### WP-A — prompts (`agents/analyst/prompts.py`)
Style (Class 4, as spec 01's `agents/ingestion/prompts.py`): Markdown headers in the order Role →
Rules → context → Style → Output → retries → Reminder; positive framing; no all-caps; data
sections are declared data, fenced, backtick runs ≥ 3 → apostrophes. System prompts hold no
per-call data. `ONLY_GIVEN_DATA` is one sentence, present verbatim in all four prompts (VC-241).
Few-shots are `HumanMessage` rendered by the same code as the real message + `AIMessage(model_dump_json())`,
on invented tables and ids that are not from the sample PDFs.
- `UNDERSTAND_PROMPT`: contains `LATEST_MESSAGE_WINS` verbatim; `standalone_question` in the language
  of the latest message (copied when already standalone); parts with entities, metrics, periods,
  operations; 1–3 English search phrases, one per kind of data. No few-shot.
  Human message: `# Earlier turns` (each `Turn N` with fenced question and answer, oldest first, or
  `none`), `# Latest user message` (fenced), `# Task`.
- `SELECT_PROMPT`: contains `RULES_BLOCK` verbatim; verdict and `missing` rules (FR-210); ids only
  from the candidates. Two few-shot pairs (FR-211): a missing comparison value (`missing_data`,
  naming what the table holds) and an ambiguous column (`ambiguous`, naming both columns).
  Human message: `# Question` (fenced), `# Question parts` (numbered, with entities, metrics,
  periods, operations), `# Candidate tables` (one `candidate_block` each); retry adds
  `# Previous answer` (JSON fence) and `# Feedback to fix` (bullets); then `# Task`.
- `candidate_block(entry)`: id, name, description, `Document: <file>, pages …`, at most 40 columns as
  `- name (unit, dtype): description` with the description cut to 60 characters, the first 20 row
  headers (with `… and N more` from `row_headers_total`), the preview fenced. If the block is still
  over 3,500 characters: drop columns from the end (adding `- … and N more columns`), then row
  headers, then preview lines from the end, until it fits. Always ≤ `MAX_CANDIDATE_CHARS`.
  The whole `select` message list (all contents summed) for 10 maximum-size candidates ≤
  `MAX_SELECT_PROMPT_CHARS`, so system prompt + few-shots + question stay under ~4,500 characters.
- `CODE_PROMPT`: contains `RULES_BLOCK` verbatim; use only `tables["<alias>"]`, pandas, numpy and the
  standard library; check needed rows, columns and values exist, else `emit` the part as `missing`
  with a reason; never estimate, interpolate or use the nearest period; state conversions in
  `approach`; end with exactly one `emit(parts)` call, whose shape is
  `[{"part": 1, "status": "answered", "values": {"label": 1.0}}, {"part": 2, "status": "missing", "missing": "why"}]`.
  One few-shot pair (FR-215): a two-part question with one part emitted `missing`; its code compiles.
  Human message: `# Question`, `# Parts to answer` (only `answerable` parts, each with its tables'
  aliases), `# Tables` (per Selected table: `tables["alias"]`, name, description, Document and
  pages, a columns table `name | dtype | unit | description` with exact names, row headers, the
  first rows = the stored preview, fenced); retry adds `# Previous attempt` (python fence) and
  `# Feedback to fix` (text fence) of `previous` only (FR-216); then `# Task`.
- `RESPOND_PROMPT`: facts only; 2–6 sentences: results first, then the method with every conversion,
  then sources as "from <Table name>, <file>, page N", then each unanswered part with its reason;
  in the language of the user's question; the Answer status is given and read-only; for
  `cannot_answer` say what is missing and what the tables contain, with no computed figure; label
  parts "Question N". No few-shot.
  Human message: `# Question` (fenced), `# Answer status`, `# Results` (per part `Question N`:
  outcome, values or reason; values omitted entirely when `cannot_answer`), `# Method` (approach),
  `# Sources`; retry adds `# Previous answer` and `# Feedback to fix`; then `# Task`.

### WP-B — checks (`agents/analyst/checks.py`)
- `check_selection`: sentences from the module constants, in this order: per entry in order, unknown
  ids (`UNKNOWN_TABLE_FEEDBACK`), extra part (`EXTRA_PART_FEEDBACK`), `answerable` with empty
  `table_ids` (`NO_TABLE_FEEDBACK`), empty `missing` when verdict ≠ `answerable`
  (`EMPTY_MISSING_FEEDBACK`, blank after `strip()` counts as empty); then per plan part
  in number order, `MISSING_PART_FEEDBACK` / `DUPLICATE_PART_FEEDBACK` (once per part).
- `classify_attempt`: order in the docstring. Python error feedback = `stderr[-2000:]`. Invalid
  output: last non-blank stdout line; `json.loads` failure or not a dict with a `parts` list →
  `EMIT_FEEDBACK + " " + NOT_JSON_DETAIL`; a Pydantic error → `EMIT_FEEDBACK + " "` + the errors as
  `<loc joined by '.'>: <msg>` joined by `"; "` (never the input values). Wrong parts:
  `WRONG_PARTS_FEEDBACK` (expected sorted, comma-separated) + the non-empty of `WRONG_PARTS_MISSING`,
  `WRONG_PARTS_EXTRA`, `WRONG_PARTS_REPEATED`, joined with spaces.
- `merge_status` (D-089 rows): selection `answerable` + emitted `answered` → `answered` with values;
  `answerable` + emitted `missing` → `missing` with the emitted reason (`EMPTY_MISSING_REASON` if
  blank); not `answerable` → `missing` with the selection's `missing`; `answerable` and `failed`
  (or no emitted entry) → `failed` with `FAILED_PART_REASON`. Status: all answered → `answered`;
  some → `partial`; none → `cannot_answer`.
- `check_numbers` (S02-D-005): number tokens `\d+(?:[.,]\d+)*`; each read English-style (`,`
  thousands, `.` decimal) and Spanish-style (`.` thousands, `,` decimal) where well-formed (thousands
  groups of exactly 3 digits). A token passes if any reading equals, within half a unit of its shown
  decimals, the absolute value of: a numeric `values` entry of an answered outcome; that value ×
  1000^k (k = −3 … 3) when a scale word follows (`thousand(s)`, `million(s)`, `billion(s)`, `k`,
  `M`, `bn`, `mil`, `millón`, `millones`, `miles`); that value × 100 when `%`, `percent` or `por
  ciento` follows. It also passes if it equals any number written in the facts' text (question, part
  texts and fields, reasons, approach, value labels, string values, table names, file names), a page
  of a table, or a part number. Returns one `NUMBER_FEEDBACK` sentence per offending number.
- `template_answer` (S02-D-009): lines joined with a space: per answered part `Question N: label =
  value; label = value.`; then `Method: <approach>` (only with an answered part and a non-blank
  approach, ending with a period); then `Sources: <name> (<file>, page 3); <name> (<file>, pages 4, 5).`
  (when tables); then per unanswered part `Question N could not be answered: <reason>` (period
  added if missing). Numbers: ints with `,` thousands; floats rounded to 4 decimals, trailing zeros
  dropped, `,` thousands. `cannot_answer` → no values even if present.

### WP-C — prelude (`agents/analyst/prelude.py`)
- `make_aliases` (S02-D-006): Table name → ASCII (NFKD, drop accents) → lowercase → every run of
  non-`[a-z0-9]` → `_` → strip `_`; cut to `MAX_ALIAS_LENGTH` at the last `_` within the limit (hard
  cut if none); empty → `table`; leading digit → prefix `t_`; repeats get `_2`, `_3` in order.
- `prelude_source` (S02-D-007): `import json`, `import math`, `import numpy as np`, `import pandas as
  pd`; `tables = {<repr(alias)>: pd.read_parquet(<repr(f"{WORK_DIR}/{table_id}.parquet")>), …}`;
  `def emit(parts)` that binds the modules it uses as default arguments (later code may reuse the
  names), and for each part: a non-dict passes unchanged; numpy scalars anywhere (`part`, values)
  become Python via `.item()`; an `answered` part with any value that is None, NaN, ±inf, a bool,
  `pd.NA` / `NaT`, or not int / float / str → `{"part": n, "status": "missing", "values": {},
  "missing": EMPTY_VALUE_REASON}`; a non-`answered` part keeps `part`, `status`, `missing` and gets
  `values: {}`. Prints `json.dumps({"parts": cleaned}, allow_nan=False)` (ASCII) with `flush=True`.

## Public interfaces
- Sandbox results: frozen `SandboxResult(exit_code, timed_out, stdout, stderr)` and
  `DockerStatus(outcome)` (`ok | unreachable | image_missing`, fixed developer `reason`) → `services/sandbox.py`.
- `make_docker_client() -> DockerClient`, `translate_sandbox_errors()` (context manager),
  `prepare_run_folder(script, table_files, *, base_dir=None) -> Path`,
  `run_script(folder, timeout_s, client=None) -> SandboxResult`,
  `check_docker(client=None) -> DockerStatus` → `services/sandbox.py` (S02-D-012/013).
- `FALLBACK_RUN_DIR` = repo `data/sandbox_runs/`; `SANDBOX_IMAGE`, `BUILD_COMMAND`,
  `OUTPUT_CAP_BYTES` = 65,536 → `services/sandbox.py`.
- `Startup.docker_status` (fourth field; settings error remains third), `load_startup()` checks
  index and sandbox → `ui/startup.py`; `SANDBOX_SECTION` → `ui/error_screen.py`.
- `Clients.docker` (zero-argument factory), `check_sandbox(factory)` → `services/health.py`.
- `FakeDockerClient(reachable=True, image_present=True, exit_code=0, timed_out=False,
  stdout=b"", stderr=b"", create_error=None)` → `tests/analyst_stubs.py`; records `create_calls`,
  `image_lookups`, `closed`, and `container.started/killed/removed/wait_timeouts`.
- Settings: `Settings.ANALYST_MAX_RETRIES`, `Settings.SANDBOX_TIMEOUT_SECONDS` → `services/settings.py`.
- Errors: `SandboxError`, `SandboxUnavailableError(user_message)` → `services/errors.py`.
- Models and shapes → `agents/analyst/schemas.py`.
- Prompts: `RULES_BLOCK`, `LATEST_MESSAGE_WINS`, `ONLY_GIVEN_DATA`, `UNDERSTAND_PROMPT`,
  `SELECT_PROMPT`, `CODE_PROMPT`, `RESPOND_PROMPT`, `SELECT_EXAMPLES`, `CODE_EXAMPLE`, `candidate_block`, `build_understand_messages`,
  `build_select_messages`, `build_code_messages`, `build_respond_messages` → `agents/analyst/prompts.py`.
- Checks: `check_selection`, `classify_attempt`, `merge_status`, `check_numbers`, `template_answer`,
  `SELECTION_FAILED_REASON`, `FAILED_PART_REASON` → `agents/analyst/checks.py`.
- Prelude: `make_aliases`, `prelude_source`, `WORK_DIR`, `EMPTY_VALUE_REASON` → `agents/analyst/prelude.py`.
- Test builders: `catalog_entry(...)`, `query_plan(*texts, search_phrases=...)` → `tests/analyst_stubs.py`.

## Conventions & invariants
- Spec 01's conventions hold (leaf errors only, no `os.environ` outside settings, LF files, tests
  offline with Given/When/Then comments and the VC id in each docstring).
- Analyst tests are named `test_analyst_*.py` where a spec 01 test has the same topic
  (`test_prompts.py` is spec 01's).
- Analyst stubs go in `tests/analyst_stubs.py` until Iteration 5 (D-105).
- The Answer status comes only from `merge_status` (BR-202); prompts never decide it.
- Values reach `respond` only for `answered` outcomes (FR-228).
- SDK `create` + `start` replaces the plan's `run` to prevent implicit image pulls (S02-D-013).
- `prepare_run_folder` owns its newly created directory; pass only its returned folder to
  `run_script`, which removes it even on a service failure. Folder/files are 0755/0644.
- Caller-injected clients remain open after `run_script`/`check_docker`; internal clients close.
  Health owns the client from its factory and closes it after the check.
- Timeout is an attempt result, not an infrastructure error; result exit code is 137 on timeout.
  Stdout/stderr keep the last 64 KB each, streamed and decoded as UTF-8 (S02-D-014).
- Infrastructure exceptions become a chained `SandboxUnavailableError` with a generic message;
  raw details remain DEBUG-only. Services never import agents.

## Commands
```bash
.venv/bin/python -m pytest -q    # 665 passed, 1 live test deselected in 39.54 s after Iteration 2
.venv/bin/python -m pytest -q tests/unit/test_sandbox.py tests/unit/test_sandbox_health.py tests/functional/test_sandbox_startup.py tests/unit/test_health.py tests/unit/test_check_services.py tests/unit/test_error_screen.py tests/functional/test_error_screen.py
.venv/bin/python -m pytest -q tests/unit/test_analyst_prompts.py tests/unit/test_analyst_checks.py tests/unit/test_prelude.py tests/unit/test_settings.py tests/unit/test_errors.py tests/unit/test_analyst_pieces.py tests/unit/test_analyst_stubs.py
```
On this Windows machine the venv is a WSL one: `wsl.exe --cd "<repo as /mnt/c/...>" -- .venv/bin/python -m pytest -q`.

## Known gaps
- The existing WSL virtual environment lacks `docker==7.1.0`. Fake-client tests do not need it;
  production startup reports unavailable. No dependency was installed or image built/pulled.
- `SANDBOX_SECTION` is the final iteration's README title; the section is intentionally not
  written until Iteration 5. Exhaustive VCs deferred under D-118 are listed in Iteration 2's record.
- Real image compatibility, daemon isolation, file sharing and timings remain student live checks.
- `prepare_run_folder` copies the supplied complete script; Iteration 3's `execute` node adds the
  prelude and supplies only Selected table paths. Pass `base_dir=FALLBACK_RUN_DIR` when needed.
- Zero Question parts or more than 3 search phrases from `understand` are handled in Iteration 3
  (S02-D-001), not by the model class.
- `template_answer` is English only; `respond` writes in the question's language.
- `merge_status` keeps the first of two emitted entries for one part (cannot happen after a valid
  classification, which rejects repeats).
- The `select` question and parts are not capped (S02-D-011): a very long question with 10
  maximum-size candidates can pass 40,000 characters.
- Spec v0.7 now folds the selection addition (D-117) and no method for `cannot_answer` (D-119).
