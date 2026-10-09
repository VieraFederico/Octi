# Iteration 03 — Service-check script and simplicity audit

Commit SHA: (filled by student). Previous iteration (02) committed as `4cd063a`.

## Criteria
| Criterion | Command | Result |
|---|---|---|
| VC-012a, 019, 019a, 020, 021, 021a, 022, 022a, 023, 024 (+ FR-008 LiteLLM / LangSmith mapping) | `pytest -q tests/unit/test_health.py tests/unit/test_check_services.py` | PASS |
| VC-011 without the abstract guard; no `IndexNotFoundError` left | `pytest -q tests/unit/test_errors.py`; `grep -rn IndexNotFoundError services tests scripts` → none | PASS |
| `conftest.py` has no stub classes; no `from tests.conftest` / test-module imports | `grep` over `tests/` → none | PASS |
| Earlier tests still pass; suite < 30 s | `.venv/bin/python -m pytest -q` | PASS — 108 passed in 2.24 s |
| Student runs `python -m scripts.check_services` against real services | — | PENDING (student) |

## Files
Added: `services/health.py`, `services/tracing.py`, `tests/unit/test_tracing.py`, `scripts/check_services.py`, `tests/fakes.py`,
`tests/unit/{test_health,test_check_services}.py`, `README.md`, this record.
Changed: `services/llm.py` (`translate_proxy_errors`), `services/errors.py` (guard and
`IndexNotFoundError` removed), `tests/conftest.py` (wiring only), `tests/unit/{test_errors,test_llm,
test_settings,test_harness_guards,test_logging_setup,test_setup_index,test_vector_store,
test_no_environ_reads}.py`, `.env.example` (model ids), `specs/00-foundation.md` (v0.6),
`specs/00-foundation-plan.md`, root `DECISIONS.md` (D-021 wording, D-027 amended, D-033),
`CONTEXT.md`, `DECISIONS.md` (S00-D-010 … 016).

## Deviations
- Scope grew with the simplicity audit (spec v0.6, S00-D-015); the plan's Iteration 3 was rewritten first.
- `models` check kept although first proposed for removal: it catches mistyped model ids (D-033 trap).

## Gotchas
- The `.env` hook blocks Bash commands whose text mentions `.env` (even inside code being written);
  edit such files with the Edit/Write tools, which are checked by target path.
- `langsmith.Client(...)` sends `GET /info` on construction; never build it in offline tests.
- openai 3.x uses `httpx2`; fake openai errors need `httpx2.Request` / `httpx2.Response`.
- LangChain silently drops `temperature` for model ids starting with `gpt-5` (except `-chat`).

## For the next iteration
- The app's startup must not call `run_checks` (D-025); use `get_settings()` + `check_index()` only.
- Show `IndexStatus.reason` / `user_message` as-is; recovery advice belongs in the module that owns
  the failure (e.g. `vector_store.py` writes the index reasons) — the UI renders, it does not rebuild.
- Put new stubs in `tests/fakes.py`; keep `conftest.py` to pytest wiring.
