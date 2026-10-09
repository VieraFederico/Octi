# Iteration 02 — LiteLLM factories, Pinecone index check and setup script

Commit SHA: (filled by student). Previous iteration (01) committed as `6a462a5`.

## Criteria
| Criterion | Command | Result |
|---|---|---|
| VC-008, 009, 010, 010a (+ BR-003 repr check) | `pytest -q tests/unit/test_llm.py` | PASS |
| VC-015, 016, 018, 018a, VC-012 (ensure part), BR-004 zero writes | `pytest -q tests/unit/test_vector_store.py` | PASS |
| VC-012 (setup-script part), VC-015, 016, 017, BR-007 | `pytest -q tests/unit/test_setup_index.py` | PASS |
| Earlier tests still pass; suite < 30 s | `.venv/bin/python -m pytest -q` | PASS — 77 passed in 8.61 s |

## Files
Added: `services/llm.py`, `services/vector_store.py`, `scripts/setup_index.py`,
`tests/unit/{test_llm,test_vector_store,test_setup_index}.py`, this record.
Changed: `tests/conftest.py` (`StubPineconeClient`), `CONTEXT.md`, `DECISIONS.md` (S00-D-006 … 009).

## Deviations
- Added `make_pinecone_client` (not named in the plan) so the Pinecone key is unwrapped in one factory (S00-D-009).
- `ensure_index` returns `"created" | "already exists"` (plan left the return type open).
- VC-017 says output shows "expected 1536, actual 3072"; the message is
  "…expected 1536 dimensions / cosine, actual 3072 dimensions / cosine." — the test asserts both
  "expected 1536" and "actual 3072".

## Gotchas
- pinecone 10 is a new SDK: errors are in `pinecone.errors.exceptions` (`UnauthorizedError`, not the old
  `UnauthorizedException`, though aliases exist). `create_index(timeout=None)` waits forever.
- `IndexModel.dimension` / `.metric` are deprecated shortcuts (S00-D-007).
- Collection is slow on `/mnt/c` (~8 s, mostly LangChain/Pinecone imports); tests themselves are < 1 s.
- `setup_index.main` calls `configure_logging`, which attaches a handler to the root logger bound to
  the stderr of that moment; under pytest it stays attached after the test (harmless today).

## For the next iteration
- Translate LiteLLM/LangSmith errors in the service check the same way as `_translate_pinecone_errors`
  (openai exceptions: `APIConnectionError`, `APITimeoutError`, `AuthenticationError`, `NotFoundError`…).
- Reuse `check_index` for the Pinecone line of the service check (`IndexStatus.outcome` / `.reason`).
- Follow the `main(settings=None, client=None) -> int` seam for `scripts/check_services.py`.
