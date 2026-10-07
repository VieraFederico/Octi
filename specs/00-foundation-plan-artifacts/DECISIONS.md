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
