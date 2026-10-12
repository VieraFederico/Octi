# Iteration 06 — The run in the chat + The catalog in the UI

Commit SHA: (filled by student).
Previous graph implementation (Iteration 5): `0e10420`; its record was committed in `5a61b7e`.
Spec version: **1.0**, including the v1.0 Changelog / D-116 findings.
Mode: one agent, interactive; staged verification (D-118). Stop after this iteration.

## Scope and criteria
- PASS — every scoped feature implemented: in-memory PDF submission; hash-first upload checks;
  duplicate Keep/Open and replacement Cancel/Replace modals; catalog retry/refusal; live status;
  both graph pause payloads/resume choices; persistent cards/skipped parts/image notes; later question
  placeholder; busy controls; New chat abandonment; session catalog/result updates; Library grouping
  and non-typeable filter; newest-first sidebar Documents with local expanders and navigation.
- PASS — smoke tests written first and seen failing: initial run had six collection errors for
  missing UI modules/runner; the sidebar navigation smoke then failed with an unsupported argument.
  The superseded PDF placeholder tests failed as expected before their deliberate update.
- PASS — offline UI regression run: `wsl .venv/bin/python -m pytest -q tests/unit/test_table_card.py
  tests/functional/test_ingestion_flow.py tests/functional/test_library.py tests/functional/test_app.py
  tests/functional/test_new_chat_modal.py tests/functional/test_error_screen.py
  tests/functional/test_sandbox_startup.py` (join lines): **28 passed**.
- PASS — full offline suite: `wsl .venv/bin/python -m pytest -q`: **665 passed, 1 deselected**, 39.44 s.
  This includes all new unit/UI smoke tests and both specs' existing offline tests; guards block network.
- PASS — artifacts updated; `git diff --check` for owned files clean. No live checks, installations,
  secret-file access, commits or pushes performed.

## Deferred to the final iteration (D-118)
The smoke tests exercise parts of these VCs; complete individual verification remains in Iteration 7:
- VC-101, VC-102, VC-103, VC-104: attachment path/no PDF on disk, all modal actions, replacement count,
  and text ordering through successful, cancelled and failed runs.
- VC-148, VC-149, VC-150: every status/route, both pauses, complete multi-card/skipped/image summary,
  and history persistence across navigation/reruns.
- VC-152, VC-153, VC-154, VC-155: startup catalog reads, ordering/dates, no post-run reload,
  all filtering/navigation actions, escaping and browser-owned expansion.
- VC-170, VC-171: full streaming/paused/finished disablement matrix and New chat cleanup through
  both warning modes, with unchanged records/files.
- VC-172, VC-173: complete failed-load/retry/refusal/recovery flows in AppTest.
- VC-166 / NFR-107: student browser checks at 1280×800 and 375 px, real attachments and component clicks.
- Iteration 5's deferred VC-105/106/107 (graph), VC-144 (graph), VC-167 (checkpoints), VC-168 (graph)
  remain outstanding as recorded there. Spec 00 VC-025b/031 regressions remain green.

## Exact files for this iteration
Created:
- `ui/catalog.py`
- `ui/ingestion.py`
- `ui/table_card.py`
- `ui/upload.py`
- `tests/unit/test_catalog_ui.py`
- `tests/unit/test_ingestion_ui.py`
- `tests/unit/test_table_card.py`
- `tests/unit/test_upload.py`
- `tests/functional/test_ingestion_flow.py`
- `tests/functional/test_library.py`
- `specs/01-ingestion-plan-artifacts/iterations/06-chat-and-catalog-ui.md`

Changed:
- `app.py`
- `assets/styles.css`
- `ui/chat.py`
- `ui/documents.py`
- `ui/library.py`
- `ui/new_chat.py`
- `ui/sidebar.py`
- `tests/stubs.py`
- `tests/functional/conftest.py`
- `tests/unit/test_chat.py`
- `tests/unit/test_documents.py`
- `specs/01-ingestion-plan-artifacts/CONTEXT.md`
- `specs/01-ingestion-plan-artifacts/DECISIONS.md`

Deleted: none. Spec 02 code, startup/error-screen changes and its new tests belong to the other agent.

## Decisions, deviations and gotchas
- S01-D-024: student-approved local v2 component retains the existing HTML expanders while sending
  Document clicks to Python; no dependency added. Register inside the active app runtime.
- Student approved shared `ui/chat.py` / `tests/stubs.py` edits and the ready-sandbox factory in
  `tests/functional/conftest.py` after concurrent spec 02 startup changes. The latter preserves
  sandbox failure tests, which override that factory. No spec 02 implementation file was edited.
- AppTest cannot attach PDFs or execute component JavaScript; pending-upload injection and escaped
  markup cover the offline seam. Existing VC-028/028a placeholder tests were deliberately replaced.
- Streaming controls render before the blocking graph call. Session keys/message shape and stub
  runner format are documented in CONTEXT.md. Graph/store remain together in the session runtime.

## For the next iteration
Iteration 7 consolidates exhaustive VC coverage (including both deferred lists), collects the
student's live/browser checks and updates the README. Do not advance until student review/commit.

Suggested summary: `Spec 01 · Iter 6: Add ingestion chat flows, upload checks and the catalog UI with staged verification (D-118)`.
