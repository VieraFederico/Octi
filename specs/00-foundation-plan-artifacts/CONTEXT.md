# CONTEXT — Spec 00 Foundation (after Iteration 2)

## Current state
- Typed configuration: `.env` (repo root) → `os.environ` → `Settings` (Pydantic), parsed once, fail-fast with names only.
- Error tree of D-027 exists; abstract bases raise `TypeError` when instantiated.
- Logging with a redacting formatter (secrets → `***`, tracebacks included).
- LiteLLM factories (chat + embeddings) and the Pinecone index check / creation, with Pinecone errors mapped to leaves.
- `python -m scripts.setup_index` creates the index or reports "already exists" / mismatch.
- Offline pytest harness: autouse guards block sockets and loading the real `.env`. No UI, no service check yet.

## File map
- `services/settings.py` — `REPO_ROOT`, `ENV_FILE`, `MIN_SECRET_LENGTH`, `load_environment`, `Settings`, `get_settings`. Only module allowed to read `os.environ`.
- `services/errors.py` — D-027 error tree.
- `services/logging_setup.py` — `configure_logging`, `RedactingFormatter`.
- `services/llm.py` — `make_chat_model`, `make_embeddings` (no retry wrapper).
- `services/vector_store.py` — constants, `IndexStatus`, `IndexClient` protocol, `make_pinecone_client`, `check_index`, `ensure_index`; private `_describe`, `_translate_pinecone_errors`.
- `scripts/setup_index.py` — `main(settings=None, client=None) -> int`.
- `tests/conftest.py` — guards (`block_network`, `block_repo_env_file`), fixtures (`fake_env`, `make_settings`), helper `env_without`, `StubPineconeClient`, fake key constants.
- `tests/unit/` — settings, errors, logging, harness guards, no-environ-reads scan, llm, vector_store, setup_index.
- `requirements.txt`, `pytest.ini`, `.env.example`, `.gitignore`.
- Empty packages: `ui/`, `tests/functional/`, `tests/live/`; folders `assets/logo/`, `assets/logo/error/`.

## Public interfaces
- `load_environment(env_file: Path | None = None) -> bool` — `load_dotenv(..., override=False)`; default `ENV_FILE` read at call time.
- `Settings.from_mapping(mapping) -> Settings` — empty values = missing; raises `InvalidSettingsError`.
- `Settings.secret_values() -> list[str]` — only for the log redactor.
- `get_settings() -> Settings` — `lru_cache`d; tests call `get_settings.cache_clear()` (the env guard does it).
- Settings fields (upper-case, spec §7): `LITELLM_BASE_URL` (normalised to one `/v1`), `LITELLM_API_KEY`, `LLM_MODEL`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSION`=1536, `LLM_TEMPERATURE`=0, `LLM_TIMEOUT_SECONDS`=60, `LLM_MAX_RETRIES`=2, `LANGSMITH_TRACING`=True, `LANGSMITH_API_KEY` (None allowed when tracing off), `LANGSMITH_PROJECT`, `LANGSMITH_ENDPOINT`, `LANGSMITH_WORKSPACE_ID`, `PINECONE_API_KEY`, `PINECONE_INDEX_NAME`="octi-tables", `PINECONE_NAMESPACE`="octi", `LOG_LEVEL`="INFO".
- Errors: leaves take `user_message: str`, except `InvalidSettingsError(problems: Mapping[str, str])` (`.problems`, `.fields`) and `IndexMismatchError(expected=(dim, metric), actual=(dim, metric))`. `ExternalServiceError` descendants have class attr `service` ("LiteLLM" | "Pinecone" | "LangSmith").
- `configure_logging(settings, stream=None)` — idempotent (replaces its own handler).
- `make_chat_model(settings) -> ChatOpenAI`, `make_embeddings(settings) -> OpenAIEmbeddings` — key passed as `SecretStr`; `timeout=LLM_TIMEOUT_SECONDS`, `max_retries=LLM_MAX_RETRIES`; embeddings use `check_embedding_ctx_length=False`.
- `make_pinecone_client(settings) -> pinecone.Pinecone` — no network on construction.
- `IndexStatus(outcome, expected_dimension, expected_metric, actual_dimension=None, actual_metric=None, reason="")` — frozen dataclass; `outcome` ∈ `"ok" | "missing" | "mismatch" | "unreachable"`; `reason` is UI-safe (empty for `ok`; contains `SETUP_COMMAND` for `missing`).
- `check_index(settings, client=None) -> IndexStatus` — read-only, never raises for Pinecone failures.
- `ensure_index(settings, client=None) -> "created" | "already exists"` — raises `IndexMismatchError`, `VectorStoreAuthenticationError`, `VectorStoreUnreachableError` (cause chained).
- `IndexClient` protocol: `describe_index(name)` (raises `pinecone.NotFoundError` when missing; result has `.dimension`, `.metric`) and `create_index(*, name, dimension, metric, spec, timeout)`.
- Constants: `PINECONE_CLOUD="aws"`, `PINECONE_REGION="us-east-1"`, `PINECONE_METRIC="cosine"`, `INDEX_READY_TIMEOUT_SECONDS=120`, `SETUP_COMMAND="python -m scripts.setup_index"`.
- `scripts.setup_index.main(settings=None, client=None) -> int` — 0 = created / already exists; 1 = any `AppError` (message on stderr).

## Conventions & invariants
- Raise only leaf errors; chain library errors with `from exc`; show only `user_message` to users.
- Pinecone exceptions are translated only inside `services/vector_store.py` (`_translate_pinecone_errors`, S00-D-006); raw causes are logged at DEBUG.
- Never read `os.environ` outside `services/settings.py` (test `test_no_environ_reads.py` enforces it).
- Scripts and services take injectable `settings` / `client` for tests; production passes nothing.
- Tests: Given/When/Then comments, VC id in each docstring, fake keys from `tests/conftest.py`, `make_settings(**overrides)` (value `None` removes a key), `StubPineconeClient(index=(dim, metric) | None, error=exc)` with `.write_calls`.
- Course reuse is credited by title ("the course's Lab 01 (Knowledge) / Lab 02 (Memory) — see README › Credits"), never by `sources/` path.

## Commands
```bash
# student, once: create venv and install
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
pytest -q                        # offline suite (live tests excluded by pytest.ini)
python -m scripts.setup_index    # student only: real Pinecone, real .env
pytest -m live -q                # live tests (none yet)
```

## Known gaps
- Service check (`services/health.py`, `scripts/check_services.py`, LiteLLM/LangSmith error mapping) → Iteration 3.
- `IndexNotFoundError` is declared but not raised yet (spec 01 query path uses it).
- Streamlit app → Iterations 4–5. README (incl. Credits for Lab 01 and Lab 02) → Iteration 6.
- `setup_index` has not been run against real Pinecone (student runs it).
