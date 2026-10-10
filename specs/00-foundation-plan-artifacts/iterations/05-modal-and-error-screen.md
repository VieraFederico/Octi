# Iteration 05 — "New chat" confirmation modal and Octi error screen

Commit SHA: (filled by student). Previous iteration (04) committed as `b220669`.

## Criteria
| Criterion | Command | Result |
|---|---|---|
| VC-030, 030a, 030b, 030c (pure decisions) | `pytest -q tests/unit/test_new_chat.py` | PASS (6) |
| VC-030 … 030d (AppTest, clicks inside the dialog) | `pytest -q tests/functional/test_new_chat_modal.py` | PASS (7) |
| VC-033a (bubble frame, 48-char lines, escaping, tail) | `pytest -q tests/unit/test_bubble.py` | PASS (6) |
| VC-032, 033, 033a (no reason echoed), 033b (frame fallback), README sections exist | `pytest -q tests/unit/test_error_screen.py` | PASS (13) |
| VC-032, 033 in the running app (no shell, no exception, no key) | `pytest -q tests/functional/test_error_screen.py` | PASS (4) |
| Earlier tests still pass; suite < 30 s | `.venv/bin/python -m pytest -q` | PASS — 182 passed in 22.1 s |
| Student breaks a variable, sees the error screen, checks 375 px stacking (part of VC-043) | — | PENDING (student) |

Each new test file was run before its module existed (RED: import error, or modal not opening), then
made to pass.

## Files
Added: `ui/{bubble,new_chat,error_screen}.py`; `tests/unit/{test_bubble,test_new_chat,test_error_screen}.py`;
`tests/functional/{test_new_chat_modal,test_error_screen}.py`; this record.
Changed: `app.py` (error screen, dialog call); `ui/startup.py` (`Startup` holds facts, `.ok`);
`ui/sidebar.py` ("New chat" → `request_new_chat`); `ui/chat.py` (`clear_conversation` removed);
`assets/styles.css` (`--octi-red`, red Erase, error layout, bubble, ≤ 640 px stacking);
`tests/stubs.py` (`MISMATCH_INDEX`, `UNREACHABLE_INDEX`); `tests/functional/test_app.py` (three interim
tests removed, now covered by the two new files); spec FR-025c; `CONTEXT.md`; `DECISIONS.md`
(S00-D-020 … 023).

## Deviations
- `Startup.problem` (Iteration 4's hand-off) was replaced by facts + `.ok` (S00-D-020, student's choice).
- FR-025c amended: "New chat" always shows the Chat view; with an empty conversation it changes nothing
  else (S00-D-023). Before, the plain clear did the same.
- Plan's flagged risk (AppTest and `st.dialog`) did not happen: AppTest clicks Erase / Cancel and ticks
  the checkbox, because the open state is a session-state flag (S00-D-023).

## Gotchas
- The `.env` guard hook blocks any Bash command whose *text* contains `.env`, even a heredoc
  that only edits a docstring mentioning it: edit such files with the Edit tool.
- 23 files in the working tree had been rewritten with CRLF endings (no content change). Files touched
  this iteration were normalised back to LF so their diffs show only real changes; the rest are still
  CRLF in the working tree (the student decides: `git checkout -- <file>` restores them).
- A click inside `st.dialog` reruns only the dialog; anything else on the page (the chat) needs `st.rerun()`.
- A checkbox inside the dialog is forgotten by Streamlit once the dialog stops being drawn, so the next
  modal starts unticked without extra code (VC-030b).
- A JetBrains Mono character is 0.6 em wide; the narrow-screen bubble font is computed from that.

## For the next iteration
- README (Iteration 6) must keep the step titles "Configure your secrets", "Create the Pinecone index"
  and "Check every service" under "Getting started", or rename them together with the constants in
  `ui/error_screen.py` (a unit test catches a mismatch).
- VC-043 manual list now includes: error screen stacking at 375 px, red Erase, modal flow by hand.
- Every root `DECISIONS.md` entry and S00-D-001 … 023 must be reflected in the README or judged internal.
