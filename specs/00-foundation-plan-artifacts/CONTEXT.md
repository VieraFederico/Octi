# CONTEXT — Spec 00 Foundation (after Iteration 6: spec 00 complete, starting state for spec 01)

## Current state
- Typed configuration: `.env` (repo root) → `os.environ` → `Settings`, parsed once, fail-fast with names only.
- Error tree (D-027, amended): group classes for `except`, leaves raised with a safe `user_message`.
- Redacting logging on Octi's own handler; LiteLLM factories; Pinecone index check / creation.
- Two CLIs: `python -m scripts.setup_index` and `python -m scripts.check_services`.
- Streamlit shell (`streamlit run app.py`): Catppuccin theme, one-screen sidebar ("Octi" home, New chat, Library, Documents preview, status popover); chat-model
  picker in the composer (`LLM_MODEL` + `LLM_MODEL_CHOICES`); swimming ASCII Octi, animated Octi logo, chat history with placeholder replies, PDF-only composer.
- "New chat" with messages asks first (modal: Erase / Cancel / "Don't warn me again", session-scoped opt-out).
- Invalid configuration or a non-`ok` index → the Octi error screen (talking Octi + ASCII speech bubble) instead of the shell.
- Offline pytest harness (network and real `.env` blocked): unit + AppTest functional tests; one live smoke test (`pytest -m live`).
- README (D-043): setup guide in D-023 order, project architecture (file tree), design decisions (titled bullet lists), Credits
  (guarded by `test_readme.py`). Written for the grader: no page map, troubleshooting, known-limits or logo-editing sections. Assignment §9 requires
  known limitations, an architecture diagram of both graphs and design decisions: spec 03 adds them.

## File map
- `services/settings.py` — configuration boundary; the only module that reads `os.environ`.
- `services/errors.py` — the error tree.
- `services/logging_setup.py` — `configure_logging` and the redacting formatter.
- `services/llm.py` — LiteLLM: chat / embeddings factories, `list_proxy_models`, `translate_proxy_errors`.
- `services/vector_store.py` — Pinecone client factory, `check_index` (read-only), `ensure_index` (creates).
- `services/tracing.py` — LangSmith: `make_langsmith_client`, `translate_tracing_errors`.
- `services/health.py` — orchestration only: the service checks, `Clients` (one factory per service), `run_checks`.
- `scripts/setup_index.py`, `scripts/check_services.py` — thin CLIs over the services above.
- `app.py` — Streamlit entry: start-up check → error screen, or the shell (sidebar + "New chat" modal + Chat / Library).
- `ui/startup.py` — cached start-up check (`load_startup` → `Startup`, facts only); no LiteLLM call (D-025).
- `ui/error_screen.py` — error messages (what failed / what to do / README section) + screen HTML. `ui/bubble.py` — ASCII speech bubble.
- `ui/new_chat.py` — "New chat" decisions (pure, over a session-state mapping) + the `st.dialog`.
- `ui/logo.py` — frame loading + CSS-animated logo HTML. `ui/chat.py` — Chat view, `reply_to`, `submission_parts`.
- `ui/sidebar.py` — sidebar (nav + status footer). `ui/style.py` — loads `assets/styles.css` (global CSS: palette variables, explicit classes). `ui/icons.py` — SVG icons (no emojis, D-036). `ui/documents.py` — sidebar Documents preview (`load_documents()` is the spec-01 seam). `ui/library.py` — Library view (empty state).
- `.streamlit/config.toml` — Catppuccin Mocha. `assets/logo/` — 8 main frames; `assets/logo/error/` — 2 frames (D-035).
- `tests/conftest.py` — pytest wiring only: autouse guards + `fake_env`, `make_settings`.
- `tests/stubs.py` — fake keys, stubs, index statuses, `always` / `failing` / `healthy_clients`.
- `tests/unit/` — one test file per module. `tests/functional/` — AppTest tests + `conftest.py` (`start_app`).
- `tests/live/test_smoke.py` — the one live test: `run_checks()` against the real services, no FAIL line (FR-035).
- `tests/unit/test_readme.py` — README structure (VC-042 order, security and retry notes, pages, Credits last) + pinned requirements.
- `README.md`, `requirements.txt`, `pytest.ini`, `.env.example`.

## Public interfaces (owner → read the code there; spec §7 is the contract)
- Configuration: `get_settings()`, `Settings.from_mapping()` → `services/settings.py`.
- Errors: every leaf and its attributes → `services/errors.py` (tree in its docstring).
- Logging: `configure_logging(settings)` → `services/logging_setup.py`.
- Models: `make_chat_model`, `make_embeddings`, `list_proxy_models`, `translate_proxy_errors` → `services/llm.py`.
- Tracing client: `make_langsmith_client`, `translate_tracing_errors` → `services/tracing.py`.
- Index: `check_index` → `IndexStatus`, `ensure_index`, `make_pinecone_client`, constants → `services/vector_store.py`.
- Service check: `run_checks(load_settings, clients)` → `list[CheckResult]`, `Clients` → `services/health.py`.
- App start-up: `load_startup()` → `Startup(settings, index_status, settings_error)`, `.ok` → `ui/startup.py`.
- Error screen: `render_error_screen(startup)`, `error_message`, `error_screen_html`, `error_frames`, README section constants → `ui/error_screen.py`; `bubble_lines`, `bubble_html`, `BUBBLE_WIDTH` → `ui/bubble.py`.
- Conversation: session key `messages` = list of `{"role", "content"}` → `ui/chat.py`.
- New chat: `request_new_chat(state)`, `erase`, `cancel`, `render_new_chat_dialog()`; session keys `new-chat-warn`, `new-chat-confirming` → `ui/new_chat.py`.
- Logo: `load_frames(folder)`, `logo_html(frames, fps)`, `LOGO_DIR`, `ERROR_LOGO_DIR` → `ui/logo.py`.
- CLIs: `scripts.setup_index.main(settings=None, client=None)`, `scripts.check_services.main(load_settings, clients)` — exit 0 = OK, 1 = a failure.

## Conventions & invariants
- Raise only leaf errors; chain library errors with `from exc`; show only `user_message` to users.
- One module per external service holds its client factory and its error translation (S00-D-016, D-034):
  `translate_proxy_errors` (LiteLLM), `_translate_pinecone_errors` (Pinecone), `translate_tracing_errors` (LangSmith). Raw causes go to DEBUG logs only.
- Never read `os.environ` outside `services/settings.py` (lint test `test_no_environ_reads.py`).
- Code that talks to a service receives its client (or a factory) so tests pass stubs; production passes nothing.
- UI modules draw from session state and `Startup`; they never build service clients. Logic worth testing
  without Streamlit lives in pure functions (`reply_to`, `logo_html`, `bubble_lines`, `error_message`, `request_new_chat`).
- The error screen never shows an index `reason`; messages are built from status fields (VC-033a).
- A file edited on the Windows side may come back with CRLF endings; keep the repo LF (diff with `--ignore-cr-at-eol` to spot it).
- Tests: Given/When/Then comments, VC id in each docstring; stubs imported from `tests/stubs.py`;
  fixtures come from `conftest.py` by parameter name; no test imports another test module.
- Use short model ids (`gpt-5-mini`): LangChain drops `temperature` only for ids starting with `gpt-5` (D-033).
- Course reuse is credited by title in README › Credits, never by `sources/` path.

## Commands
```bash
# student, once: create venv and install
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
pytest -q                          # offline suite (live tests excluded by pytest.ini), ~26 s
pytest -m live                     # student only: the live smoke test, real .env
python -m scripts.setup_index      # student only: real Pinecone, real .env
python -m scripts.check_services   # student only: real services, real .env
streamlit run app.py               # student only: the app
```

## Known gaps
- The error screen and the modal are checked by AppTest only; the 375 px stacking and the red Erase are a manual check (VC-043).
- AppTest cannot attach files to the composer (S00-D-018): real PDF attachment is a manual check.
- Logging redaction covers Octi's handler only (spec FR-009).
- `Settings` defaults are not exported to the environment (spec A-006) — specs 01/02 must keep tracing on when a variable is omitted.
- Agents, table store and sandbox: specs 01/02. Library and sidebar Documents stay empty until spec 01 replaces `ui/documents.load_documents()`.
- The error screen points to README step titles "Configure your secrets", "Create the Pinecone index", "Check every service": rename them together with the constants in `ui/error_screen.py`.
