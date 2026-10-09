# Iteration 04 — Streamlit shell: theme, layout, logo, sidebar, composer

Commit SHA: (filled by student). Previous iteration (03) committed as `e459ca1`.

## Criteria
| Criterion | Command | Result |
|---|---|---|
| VC-025, 026, 026a, 027, 029, 031, 034, 035 (+ interim FR-027 / FR-028 errors, plain "New chat") | `pytest -q tests/functional/test_app.py` | PASS |
| VC-028, 028a (pure handlers; AppTest cannot upload, S00-D-018) | `pytest -q tests/unit/test_chat.py` | PASS |
| VC-036, 037, 038, 039 | `pytest -q tests/unit/test_logo.py` | PASS |
| Earlier tests still pass; suite < 30 s | `.venv/bin/python -m pytest -q` | PASS — 129 passed in 18.5 s |
| Student runs `streamlit run app.py`: empty state, composer moves, theme, logo (part of VC-043) | — | PENDING (student) |

## Files
Added: `app.py`, `ui/{startup,logo,chat,library,sidebar}.py`, `.streamlit/config.toml`,
`assets/logo/frame_01..08.txt`, `assets/logo/error/frame_01..02.txt`, `tests/unit/{test_logo,test_chat}.py`,
`tests/functional/{conftest,test_app}.py`, this record.
Changed: `tests/fakes.py` → renamed `tests/stubs.py` (student's request; imports updated) + `OK_INDEX`,
`MISSING_INDEX`; `specs/00-foundation.md` (FR-033, VC-039); root `DECISIONS.md` (D-035);
`CONTEXT.md`; `DECISIONS.md` (S00-D-017 … 019).

## Deviations
- `ui/startup.py` and `ui/library.py` added beyond the plan's file map (S00-D-019).
- Logo frames are the student's Octi art (D-035) instead of placeholders: 8 main frames, 2 error frames.
- Before the Octi error screen exists, start-up problems use `st.error` (planned interim).

## Gotchas
- AppTest's default timeout (3 s) is too short for the first run on `/mnt/c`; use 60 s.
- Every AppTest scans installed packages for component manifests (~3 s on `/mnt/c`); the functional
  conftest skips it (S00-D-017). The first app test still takes ~12 s (cold imports).
- `st.chat_input` inside a container renders inline (AppTest root 0); at the top level it is pinned
  to the bottom (root 3). The tests use this to check FR-020 / FR-021.
- `st.cache_resource` is process-wide: tests must clear it (the `start_app` fixture does).
- Frame newlines are emitted as `&#10;`: a blank line inside a frame would otherwise end Streamlit's
  Markdown HTML block.

## For the next iteration
- Replace the `st.error` + `st.stop()` branch in `app.py` with the Octi error screen; read
  `Startup.problem` (already safe text), plus `Startup.settings is None` (configuration) vs
  `Startup.index_status.outcome` to pick the README section.
- Reuse `ui.logo.load_frames(ERROR_LOGO_DIR)` with fallback to `LOGO_DIR`, then to `logo_html([])`.
- Wire the sidebar's "New chat" to the modal; `clear_conversation()` stays the action.
