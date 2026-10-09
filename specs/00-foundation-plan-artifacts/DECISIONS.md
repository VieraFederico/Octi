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
