# CONTEXT — Spec 00 Foundation (after Iteration 1)

## Current state
- Typed configuration: `.env` (repo root) → `os.environ` → `Settings` (Pydantic), parsed once, fail-fast with names only.
- Error tree of D-027 exists; abstract bases raise `TypeError` when instantiated.
- Logging with a redacting formatter (secrets → `***`, tracebacks included).
- Offline pytest harness: autouse guards block sockets and loading the real `.env`.
- No services, scripts or UI yet.

## File map
- `services/settings.py` — `REPO_ROOT`, `ENV_FILE`, `MIN_SECRET_LENGTH`, `load_environment`, `Settings`, `get_settings`. Only module allowed to read `os.environ`.
- `services/errors.py` — D-027 error tree.
- `services/logging_setup.py` — `configure_logging`, `RedactingFormatter`.
- `tests/conftest.py` — guards (`block_network`, `block_repo_env_file`), fixtures (`fake_env`, `make_settings`), helper `env_without`, fake key constants.
- `tests/unit/` — settings, errors, logging, harness guards, no-environ-reads scan.
- `requirements.txt`, `pytest.ini`, `.env.example`, `.gitignore`.
- Empty packages: `scripts/`, `ui/`, `tests/functional/`, `tests/live/`; folders `assets/logo/`, `assets/logo/error/`.

## Public interfaces
- `load_environment(env_file: Path | None = None) -> bool` — `load_dotenv(..., override=False)`; default `ENV_FILE` read at call time.
- `Settings.from_mapping(mapping) -> Settings` — empty values = missing; raises `InvalidSettingsError`.
- `Settings.secret_values() -> list[str]` — only for the log redactor.
- `get_settings() -> Settings` — `lru_cache`d; tests call `get_settings.cache_clear()` (the env guard does it).
- Settings fields (upper-case, spec §7): `LITELLM_BASE_URL` (normalised to one `/v1`), `LITELLM_API_KEY`, `LLM_MODEL`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSION`=1536, `LLM_TEMPERATURE`=0, `LLM_TIMEOUT_SECONDS`=60, `LLM_MAX_RETRIES`=2, `LANGSMITH_TRACING`=True, `LANGSMITH_API_KEY` (None allowed when tracing off), `LANGSMITH_PROJECT`, `LANGSMITH_ENDPOINT`, `LANGSMITH_WORKSPACE_ID`, `PINECONE_API_KEY`, `PINECONE_INDEX_NAME`="octi-tables", `PINECONE_NAMESPACE`="octi", `LOG_LEVEL`="INFO".
- Errors: leaves take `user_message: str`, except `InvalidSettingsError(problems: Mapping[str, str])` (`.problems`, `.fields`) and `IndexMismatchError(expected=(dim, metric), actual=(dim, metric))`. `ExternalServiceError` descendants have class attr `service` ("LiteLLM" | "Pinecone" | "LangSmith").
- `configure_logging(settings, stream=None)` — idempotent (replaces its own handler).

## Conventions & invariants
- Raise only leaf errors; chain library errors with `from exc`; show only `user_message` to users.
- Never read `os.environ` outside `services/settings.py` (test `test_no_environ_reads.py` enforces it).
- Tests: Given/When/Then comments, VC id in each docstring, fake keys from `tests/conftest.py`, `make_settings(**overrides)` (value `None` removes a key).
- Course reuse is credited by title ("the course's Lab 02 (Memory) — see README › Credits"), never by `sources/` path.

## Commands
```bash
# student, once: create venv and install
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
pytest -q            # offline suite (live tests excluded by pytest.ini)
pytest -m live -q    # live tests (none yet)
```

## Known gaps
- LLM factories, Pinecone index check, setup script → Iteration 2.
- Service check → Iteration 3. Streamlit app → Iterations 4–5. README → Iteration 6.
