# CONTEXT — Spec 00 Foundation (after Iteration 3)

## Current state
- Typed configuration: `.env` (repo root) → `os.environ` → `Settings`, parsed once, fail-fast with names only.
- Error tree (D-027, amended): group classes for `except`, leaves raised with a safe `user_message`.
- Redacting logging on Octi's own handler; LiteLLM factories; Pinecone index check / creation.
- Two CLIs: `python -m scripts.setup_index` and `python -m scripts.check_services`.
- Offline pytest harness (network and real `.env` blocked). Minimal README. No Streamlit app yet.

## File map
- `services/settings.py` — configuration boundary; the only module that reads `os.environ`.
- `services/errors.py` — the error tree.
- `services/logging_setup.py` — `configure_logging` and the redacting formatter.
- `services/llm.py` — LiteLLM: chat / embeddings factories, `list_proxy_models`, `translate_proxy_errors`.
- `services/vector_store.py` — Pinecone client factory, `check_index` (read-only), `ensure_index` (creates).
- `services/tracing.py` — LangSmith: `make_langsmith_client`, `translate_tracing_errors`.
- `services/health.py` — orchestration only: the service checks, `Clients` (one factory per service), `run_checks`.
- `scripts/setup_index.py`, `scripts/check_services.py` — thin CLIs over the services above.
- `tests/conftest.py` — pytest wiring only: autouse guards + `fake_env`, `make_settings`.
- `tests/fakes.py` — fake keys, stubs, `always` / `failing` / `healthy_clients`.
- `tests/unit/` — one test file per module above.
- `README.md` (minimal getting started + Credits), `requirements.txt`, `pytest.ini`, `.env.example`.
- Empty: `ui/`, `tests/functional/`, `tests/live/`, `assets/logo/`, `assets/logo/error/`.

## Public interfaces (owner → read the code there; spec §7 is the contract)
- Configuration: `get_settings()`, `Settings.from_mapping()` → `services/settings.py`.
- Errors: every leaf and its attributes → `services/errors.py` (tree in its docstring).
- Logging: `configure_logging(settings)` → `services/logging_setup.py`.
- Models: `make_chat_model`, `make_embeddings`, `list_proxy_models`, `translate_proxy_errors` → `services/llm.py`.
- Tracing client: `make_langsmith_client`, `translate_tracing_errors` → `services/tracing.py`.
- Index: `check_index` → `IndexStatus`, `ensure_index`, `make_pinecone_client`, constants → `services/vector_store.py`.
- Service check: `run_checks(load_settings, clients)` → `list[CheckResult]`, `Clients` → `services/health.py`.
- CLIs: `scripts.setup_index.main(settings=None, client=None)`, `scripts.check_services.main(load_settings, clients)` — exit 0 = OK, 1 = a failure.

## Conventions & invariants
- Raise only leaf errors; chain library errors with `from exc`; show only `user_message` to users.
- One module per external service holds its client factory and its error translation (S00-D-016):
  `translate_proxy_errors` (LiteLLM), `_translate_pinecone_errors` (Pinecone), `translate_tracing_errors` (LangSmith). Raw causes go to DEBUG logs only.
- Never read `os.environ` outside `services/settings.py` (lint test `test_no_environ_reads.py`).
- Code that talks to a service receives its client (or a factory) so tests pass stubs; production passes nothing.
- Tests: Given/When/Then comments, VC id in each docstring; fakes imported from `tests/fakes.py`;
  fixtures come from `conftest.py` by parameter name; no test imports another test module.
- Use short model ids (`gpt-5-mini`): LangChain drops `temperature` only for ids starting with `gpt-5` (D-033).
- Course reuse is credited by title in README › Credits, never by `sources/` path.

## Commands
```bash
# student, once: create venv and install
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
pytest -q                          # offline suite (live tests excluded by pytest.ini)
python -m scripts.setup_index      # student only: real Pinecone, real .env
python -m scripts.check_services   # student only: real services, real .env
```

## Known gaps
- Streamlit shell → Iteration 4; modal + Octi error screen → Iteration 5 (full UI scope kept, S00-D-015).
- Live test (one test calling `run_checks()`) and the full README → Iteration 6.
- Logging redaction covers Octi's handler only (spec FR-009).
- `Settings` defaults are not exported to the environment (spec A-006) — specs 01/02 must keep tracing on when a variable is omitted.
- The student has not yet run `check_services` against the real services.
