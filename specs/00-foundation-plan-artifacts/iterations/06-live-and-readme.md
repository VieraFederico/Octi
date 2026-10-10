# Iteration 06 — Live smoke test, end-to-end checks and the README

Commit SHA: (filled by student). Previous iteration (05) committed as `705105a`.

## Criteria
| Criterion | Command | Result |
|---|---|---|
| VC-040: offline suite passes, no network, < 30 s | `.venv/bin/python -m pytest -q` | PASS — 190 passed, 1 deselected in 26.0 s (pytest time; 40 s wall clock, Python start-up on `/mnt/c`). No network: the autouse guard fails any test that connects. |
| Live test excluded by default, selectable | `pytest --collect-only -q` / `-m live` | PASS — 190/191 (1 deselected) / 1/191 |
| VC-041: live smoke test passes | `pytest -m live` (real `.env`) | PASS — run by the student: 1 passed, 190 deselected in 11.5 s |
| VC-042: README sections in order; requirements pinned | `pytest -q tests/unit/test_readme.py` | PASS (8); RED first (4 failing on the minimal README) |
| README section titles used by the error screen exist | `pytest -q tests/unit/test_error_screen.py` | PASS |
| VC-043: manual checklist (service check < 60 s, first screen < 5 s, no horizontal scroll at 1280×800 and 375 px, centered empty state, composer moves, error screen stacks, Catppuccin colors) | — | PENDING (student) |
| Getting-started commands run in order by the student | — | PENDING (student) |
| Every decision reflected in the README or judged internal | review below | PASS |

## Decisions: README or internal
In the README: D-001, D-002, D-003, D-006, D-007, D-008, D-010, D-011, D-012, D-013, D-014, D-016 (amended by D-043),
D-017, D-018, D-021, D-023, D-024, D-025, D-026, D-027, D-029, D-030, D-031, D-032 (what the bubble
says), D-033, D-034, D-035 (Credits), D-036 (no emojis, styles.css), D-037 (model picker), D-040
(Documents list); S00-D-002 (tracebacks redacted), S00-D-004 (empty = missing), S00-D-014 (git
skipped), S00-D-016, S00-D-020 (README sections).
Internal (process, superseded, or implementation detail a user never meets): D-004, D-005, D-009
(superseded), D-015 (superseded), D-019, D-020 (logo mechanics; the student dropped the logo section),
D-022 (specs 01/02), D-028, D-038, D-039, D-041 (visual tuning); S00-D-001, 003, 005, 006, 007, 008,
009, 010, 011, 012, 013, 015, 017, 018, 019, 021, 022, 023. The README links
the root `DECISIONS.md` for the full log.

## Files
Added: `tests/live/test_smoke.py`, `tests/unit/test_readme.py`, this record.
Changed: `README.md` (rewritten: status, getting started in D-023 order, where each page lives, how it
is built, Credits); `CONTEXT.md` (final state).

## Revision after the student's review
The student rewrote the head and steps 1–2 (logo image, generic LiteLLM proxy wording) and asked for a
README for a grader and any user: generic wording for services and keys (no Pinecone cloud/region,
no university-specific proxy text), security notes as facts and recommendations (`.env` already in
`.gitignore`, `chmod 600` advised) instead of "never commit" instructions, and no logo-editing,
troubleshooting, known-limits or page-map sections (root D-043, amends D-016 / D-023 and VC-042).
Architecture is a file tree; design decisions are titled bullet lists. Added `.gitattributes`
(`* text=auto eol=lf`, root D-044): the student edits on macOS and Windows, and Windows tools had
rewritten 13 unchanged files as CRLF. `test_readme.py` now checks
`.gitignore` + `chmod 600` and no longer asks for the page map.
`pytest -q`: 191 passed, 1 deselected.
No new decisions (`DECISIONS.md` unchanged). No code change outside tests.

## Deviations
- VC-042 is checked by a unit test, not a recorded grep (the plan allowed either); the test also guards
  FR-036's security and retry notes, the §7 page map, Credits last, and no links into `specs/`.
- Credits now also name non-course sources: Catppuccin palette, Inter and JetBrains Mono fonts,
  Streamlit docs patterns, and the author's own ASCII art (assignment §11).

## Gotchas
- The `.env` guard hook blocks a Bash command whose text mentions `.env`, even a Python script that
  edits Markdown about it: use the Edit tool for such files.
- `pytest -m live` works although `pytest.ini` has `addopts = -m "not live"`: the last `-m` wins.
- The README states facts the code must keep true (e.g. setup refuses a wrong-shape index with exit 1);
  each was checked against the code before writing.

## For the next iteration (spec 01)
- `CONTEXT.md` is the starting state. Hooks: `ui/documents.load_documents()` (sidebar list),
  `ui/library.render_library()` (Library view), the composer's PDF handler in `ui/chat.py`
  (`reply_to`), `translate_proxy_errors` around agent model calls.
- Spec 01 adds its own README sections; keep "Credits" last (`test_readme.py`).
- Assignment §9 deliverable 2: the README must have known limitations, an architecture diagram of both
  graphs and design decisions (extraction library, table store, chunking/embeddings, sandbox). Spec 03
  (or 01/02 for their own choices) adds them; today's README has none of the first two.
- A-006: make sure a run is traced even when a tracing variable is omitted.
