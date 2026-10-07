# Iteration 01 — Settings, errors, logging and the offline test harness

Commit SHA: (filled by student)

## Criteria
| Criterion | Command | Result |
|---|---|---|
| VC-001, 002, 003, 004, 005, 006, 007, 007a, 007b, 007d | `pytest -q tests/unit/test_settings.py` | PASS |
| VC-007c | `pytest -q tests/unit/test_no_environ_reads.py` | PASS |
| VC-011, 011a | `pytest -q tests/unit/test_errors.py` | PASS |
| VC-013, 013a, 014 | `pytest -q tests/unit/test_logging_setup.py` | PASS |
| VC-040a, VC-040 (partial) | `pytest -q tests/unit/test_harness_guards.py` | PASS |
| Whole suite < 30 s | `.venv/bin/python -m pytest -q` | PASS — 46 passed in 0.79 s |
| Smoke run of settings/errors/logging (no pytest) | playground venv python script | PASS |

## Files
Added: `services/{__init__,errors,settings,logging_setup}.py`, `scripts/__init__.py`, `ui/__init__.py`,
`tests/{__init__,conftest}.py`, `tests/unit/{__init__,test_settings,test_errors,test_logging_setup,test_harness_guards,test_no_environ_reads}.py`,
`tests/functional/__init__.py`, `tests/live/__init__.py`, `requirements.txt`, `pytest.ini`, artifacts.
Changed: `.env.example` (all spec §7 variables), `.gitignore` (venv, caches), `specs/00-foundation.md` (BR-003 exception, S00-D-005).

## Deviations
- pytest 9.1.1 instead of "latest 8.x" (S00-D-001).
- Redaction implemented as a formatter (S00-D-002).

## Gotchas
- `LANGSMITH_API_KEY` must be declared after `LANGSMITH_TRACING` in `Settings`: its validator reads the flag from `info.data`; it uses `validate_default=True` so "missing" still runs the check.
- `AppError.__new__` checks `cls.__dict__` (not `getattr`) so leaves don't inherit the abstract flag.

## For the next iteration
- Use `make_settings()` / `fake_env` from `tests/conftest.py`; all sockets are blocked, so stub every client.
- Raise leaves from `services/errors.py`; e.g. `VectorStoreUnreachableError("…")`, `IndexMismatchError(expected=(1536, "cosine"), actual=(…))`.
- Factories must read `settings.LITELLM_API_KEY.get_secret_value()` only inside `services/llm.py`.
