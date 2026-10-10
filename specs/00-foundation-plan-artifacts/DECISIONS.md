# Spec 00 — decisions taken during implementation (S00-D-NNN)

## S00-D-001: Pin pytest 9.1.1  (Iteration 1)
**Context**: The plan said "latest stable 8.x"; PyPI's latest stable is 9.1.1.
**Decision**: Pin `pytest==9.1.1`.
**Rejected**: 8.4.2 — no reason to start a new project on the previous major.
**Consequences**: Python ≥ 3.10 required by pytest; compatible with D-007 (≥ 3.11).

## S00-D-002: Redact secrets in the formatter, not a filter  (Iteration 1)
**Context**: FR-009 says log lines must not contain secrets; a `logging.Filter` sees the message but not the formatted traceback.
**Decision**: `RedactingFormatter.format()` replaces secret values in the final text.
**Rejected**: `logging.Filter` on `record.msg` — misses `exc_info` tracebacks.
**Consequences**: Only output from Octi's handler is redacted; other handlers added by libraries are not (none today).

## S00-D-003: Test seams for configuration  (Iteration 1)
**Context**: Tests must build Settings from fake values and never load the real `.env` (BR-009).
**Decision**: `Settings.from_mapping(mapping)` for tests; `load_environment` reads the module-level `ENV_FILE` at call time so tests can point it to a temp file; an autouse fixture patches `services.settings.load_dotenv` to refuse the real repo-root path.
**Rejected**: Env-var-driven switch (e.g. `OCTI_TESTING=1`) — production code would carry test logic.
**Consequences**: New code must load env files only through `load_environment` (so the guard sees it).

## S00-D-004: Empty environment values count as missing  (Iteration 1)
**Context**: `.env.example` ships keys with empty values; `KEY=` must not pass as a valid empty string.
**Decision**: `from_mapping` drops empty values before parsing, so they report as "missing".
**Rejected**: Treating "" as a value — `LITELLM_API_KEY=` would fail with a confusing length error.
**Consequences**: Optional fields fall back to their defaults when left empty.

## S00-D-005: Log redactor may read secrets (spec BR-003 exception widened)  (Iteration 1)
**Context**: BR-003 listed only the client factories as allowed to unwrap secrets; redaction needs the values.
**Decision**: Spec BR-003 now also allows the log redactor; access goes through `Settings.secret_values()`.
**Rejected**: Hashing secrets and comparing hashes per substring — slow and pointless.
**Consequences**: `secret_values()` must only be used by logging.

## S00-D-006: How Pinecone 10.0.0 errors map to leaves  (Iteration 2)
**Context**: FR-008 needs "connection" vs "authentication" told apart; pinecone 10 rewrote its exception module.
**Decision**: Identified by reading the installed `pinecone/errors/exceptions.py`: HTTP errors are `ApiError` subclasses by status; transport failures are `PineconeConnectionError` / `PineconeTimeoutError`; all derive from `PineconeError`. Mapping: `UnauthorizedError` (401) / `ForbiddenError` (403) → `VectorStoreAuthenticationError`; `NotFoundError` on describe → "missing"; **every other `PineconeError`** (connection, timeout, 5xx, 429, parse errors) → `VectorStoreUnreachableError`.
**Rejected**: A separate leaf for 5xx/429 — the user's action is the same ("try again"), so BR-011 says reuse.
**Consequences**: Non-Pinecone exceptions (programming bugs) are not caught and surface as normal tracebacks.

## S00-D-007: Read the index shape through the SDK's `dimension` / `metric` shortcuts  (Iteration 2)
**Context**: pinecone 10 marks `IndexModel.dimension` / `.metric` as deprecated in favour of `index.schema.fields[...]`.
**Decision**: Use the shortcuts; they resolve for a single dense vector field, the only kind Octi creates. The metric may be the SDK's `Metric` str-enum, so `.value` is read when present.
**Rejected**: Walking `schema.fields` — needs the field name and more code for no gain today.
**Consequences**: A future pinecone major version may remove the shortcuts; `_describe` in `services/vector_store.py` is the one place to change.

## S00-D-008: Bounded wait for a new index (120 s)  (Iteration 2)
**Context**: `create_index(timeout=None)` (the SDK default) waits forever for readiness; the assignment forbids unbounded loops.
**Decision**: Code constant `INDEX_READY_TIMEOUT_SECONDS = 120`. A timeout becomes `VectorStoreUnreachableError` (non-zero exit).
**Rejected**: `None` (unbounded); `-1` (return at once — the first upsert in spec 01 could hit a not-ready index).
**Consequences**: On a timeout the index may still finish creating; re-running the script then reports "already exists".

## S00-D-009: Client factories and secret handling  (Iteration 2)
**Context**: BR-003 allows "the three client factories" to unwrap secrets.
**Decision**: LangChain accepts `SecretStr` directly, so `make_chat_model` / `make_embeddings` pass it without unwrapping. Only `make_pinecone_client` (in `services/vector_store.py`) calls `get_secret_value()`. The setup script exposes `main(settings=None, client=None)` as its test seam.
**Rejected**: Unwrapping in all factories (more places holding plain keys).
**Consequences**: BR-003's exception now applies in practice to one factory plus the log redactor; the spec text still reads "three factories" (allowed, not required).

## S00-D-010: Each service check builds its own client  (Iteration 3)
**Context**: The first draft built every client up front; one constructor failure (LangSmith's sends `GET /info`) turned all five service lines into FAIL without running them (simplicity audit 2026-10-09, finding 1).
**Decision**: `services.health.Clients` holds one factory per service; each `check_*` calls its factory inside its own guarded step (spec FR-017, VC-022a).
**Rejected**: An aggregate `Services` object built once; a lazy client container.
**Consequences**: A check may build a client the previous check also built (cheap, no network except LangSmith).

## S00-D-011: LiteLLM error mapping lives in `services.llm.translate_proxy_errors`  (Iteration 3)
**Context**: FR-008 for the proxy; agents in specs 01/02 need the same mapping.
**Decision**: 401/403 → `ProxyAuthenticationError`; 404 → `ModelNotAvailableError`; connection error / timeout → `ProxyUnreachableError`; any other `openai.APIError` → `ProxyUnreachableError` whose message shows only the HTTP status.
**Rejected**: A leaf per HTTP status — the user's action is the same (BR-011).
**Consequences**: Agents wrap model calls in `with translate_proxy_errors():`.

## S00-D-012: LangSmith check = tracing on + `list_projects(limit=1)`  (Iteration 3)
**Context**: FR-015 needs one authenticated request; the client constructor already makes a request.
**Decision**: Tracing off → FAIL without building a client (D-024). Otherwise build the client and read one project; `LangSmithAuthError` → `TracingAuthenticationError`, any other `LangSmithError` → `TracingUnreachableError`.
**Rejected**: `read_project(name)` — the project does not exist before the first trace (404).
**Consequences**: Client timeout = `LLM_TIMEOUT_SECONDS`.

## S00-D-013: Test layout — `conftest.py` is wiring, `tests/fakes.py` holds fakes  (Iteration 3)
**Context**: `conftest.py` mixed pytest wiring with stubs; seven test files imported from it and one test file imported another (audit finding 7).
**Decision**: `conftest.py` keeps only the autouse guards and the `fake_env` / `make_settings` fixtures. Fake keys, stubs and the factory helpers `always`, `failing`, `healthy_clients` live in the plain module `tests/fakes.py`. Fake openai errors are built with `httpx2`, the HTTP library openai 3.x uses (transitive dependency).
**Rejected**: Keeping helpers in `conftest.py` (pytest advises against importing it).
**Consequences**: "In a test's parameters → conftest; in an import line → fakes."

## S00-D-014: Git safety-net edge cases are SKIPPED, never FAIL  (Iteration 3)
**Context**: FR-016 defines OK / FAIL / skipped (not a git repository); git may also be missing or hang.
**Decision**: git not installed, timeout (10 s) or any other unexpected answer → SKIPPED with a reason. Only "the file is tracked" is a FAIL.
**Rejected**: Failing the run when git itself misbehaves — not the user's secrets problem.
**Consequences**: A SKIPPED line never changes the exit code.

## S00-D-015: Simplicity audit applied (spec v0.6)  (Iteration 3)
**Context**: Audit of 2026-10-09; the student accepted items 1, A, C, D, F, G, H, I, M and rejected B (keep the git check) and E (keep the UI polish).
**Decision**: Abstract-base guard and `IndexNotFoundError` removed (root D-027 amended); models check kept; one live test runs the service check; logging/retry/latency wording scoped; `CONTEXT.md` interfaces as pointers; minimal README now; models per root D-033; tracing-defaults watchpoint as spec A-006.
**Rejected**: Flattening the error tree to four classes (more churn than value).
**Consequences**: Iterations 4–5 keep the full UI scope; Iteration 6 writes one live test, not three.

## S00-D-016: One module per external service  (Iteration 3)
**Context**: The student asked for separation of concerns: `health.py` held the LangSmith factory, the LangSmith error mapping and the proxy model listing.
**Decision**: Each external service has one module holding its client factory and its error translation: `services/llm.py` (LiteLLM, incl. `list_proxy_models`), `services/vector_store.py` (Pinecone), new `services/tracing.py` (LangSmith; not named `langsmith.py`, which would shadow the library). `services/health.py` only orchestrates. `run_git_in_repo` stays in `health.py` (its only user).
**Rejected**: Leaving factories in `health.py`; a folder per service (too small to split today).
**Consequences**: Agents import factories and translators from the service modules, never from `health.py`.

## S00-D-017: App test seam  (Iteration 4)
**Context**: AppTest runs `app.py` in the test process; the app must start with fake settings and a fake index status.
**Decision**: `tests/functional/conftest.py` → `start_app(settings=…, index_status=…, settings_error=…)` patches `ui.startup.get_settings` and `ui.startup.check_index` (where they are used), clears `st.cache_resource`, and makes the LiteLLM factories raise if called (D-025). It also skips Streamlit's component-manifest scan, which costs ~3 s per AppTest on `/mnt/c` and finds nothing (Octi has no custom components): suite 58 s → 18 s.
**Rejected**: An environment flag read by the app (test logic in production code).
**Consequences**: `load_startup()` must keep calling `get_settings` / `check_index` through the `ui.startup` module names.

## S00-D-018: AppTest cannot upload files into `st.chat_input`  (Iteration 4)
**Context**: The plan flagged this risk; Streamlit 1.65's AppTest `ChatInput.set_value` accepts text only.
**Decision**: The PDF handling is two pure functions in `ui/chat.py` (`submission_parts`, `reply_to`) tested in `tests/unit/test_chat.py` (VC-028, VC-028a, with an upload object whose content raises if read). VC-029 reads the composer's `file_type` from the AppTest element.
**Rejected**: Driving the browser (Playwright) — a new dependency for one check.
**Consequences**: The student confirms a real PDF attachment by hand (VC-043 checklist).

## S00-D-019: Two UI modules beyond the plan's file map  (Iteration 4)
**Context**: The plan listed `ui/{logo,sidebar,chat,…}.py`.
**Decision**: Added `ui/startup.py` (the cached start-up check, `Startup` result, test seam) and `ui/library.py` (Library view; grows in spec 01). `app.py` stays a thin script.
**Rejected**: Start-up logic inside `app.py` (untestable seam); Library inside `chat.py` (unrelated view).
**Consequences**: The error screen (Iteration 5) reads `Startup` to decide what to show.

## S00-D-020: Startup holds facts; the error screen owns the words  (Iteration 5)
**Context**: Iteration 4's `Startup.problem` was ready-made text from `ui/startup.py`; the mismatch text had no fix, and VC-033a forbids echoing an index `reason`.
**Decision** (student's choice): `Startup(settings, index_status, settings_error)` with an `ok` property. `ui/error_screen.error_message` builds every message as what failed + what to do + "Read: README › <section>": config from the settings error's `user_message` (names and rules, never values); index messages from the status fields (outcome, expected/actual shape) and the index name, never from `reason`.
**Rejected**: Keep `problem` and only append the README section (wording split across two modules; the reason text would reach the screen).
**Consequences**: The README section titles are constants in `ui/error_screen.py`; `test_every_readme_section_named_on_the_screen_exists` fails if Iteration 6 renames them.

## S00-D-021: Bubble tail on the middle row, hidden when stacked  (Iteration 5)
**Context**: FR-027a asks for a tail pointing at Octi; under 640 px the bubble sits below Octi (FR-027b).
**Decision** (student's choice): `<─────┤` sticks out of the left border on the middle row; every other row has a same-width gutter so the box stays aligned. Under 640 px the CSS hides tail and gutter, shows a plain `│` in the tail's place, and shrinks the font so 52 characters fit the width.
**Rejected**: A comic tail under the bottom-left corner.
**Consequences**: The bubble is three kinds of `<span>` inside one `<pre>` (`ui/bubble.py`); the box itself stays plain text that tests read with `bubble_lines`.

## S00-D-022: Red Erase button  (Iteration 5)
**Context**: Erase is destructive; the primary color (Mauve) reads as a normal action.
**Decision** (student's choice): Erase is tinted Catppuccin Red (`--octi-red`, D-029) through its `.st-key-new-chat-erase` class; Cancel is a tertiary (text) button. Copy: title "Start a new chat?", body "This erases the current conversation. It can't be undone.", checkbox "Don't warn me again".
**Rejected**: Mauve primary.
**Consequences**: One CSS rule; no theme change.

## S00-D-023: The modal's open state lives in session state  (Iteration 5)
**Context**: A click inside `st.dialog` reruns only the dialog in the browser, but a full script run (AppTest, or `st.rerun`) does not call the dialog again unless the code does.
**Decision**: `CONFIRMING` flag in session state; `app.py` calls `render_new_chat_dialog()` every run and it opens the dialog while the flag is set. Erase / Cancel are plain `if st.button(...)` checks that clear it and call `st.rerun()` (a full rerun redraws the chat behind the modal); dismissing (X, Esc, outside click) is Cancel through `on_dismiss`. "New chat" always switches to the Chat view before deciding (FR-025c amended). `clear_conversation()` left `ui/chat.py`; clearing is `ui/new_chat.py`'s job.
**Rejected**: Calling the dialog once, when the button is clicked, with no flag: the dialog only exists in runs that call it, so the next full run (e.g. AppTest clicking Erase) would not see its buttons.
**Consequences**: AppTest drives the whole modal (VC-030 … VC-030d), so the plan's flagged risk did not materialise.
