# Iteration 4 — Analysis chat and evidence

- **Commit SHA:** (filled by student)
- **Previous iteration:** `236b2cf`; spec 01 Iteration 7 record committed before starting.
- **Mode:** one agent; Spec 02 v0.9; staged verification (D-118).

## Implemented scope
- Durable Analysis assistant message with live progress/rewrite, colored status badge, answer,
  Missing: Question N lines, folded Tables used/Code/Output/Attempts; reduced Tables considered
  layout and generic error layout. Full data loads only through Show data, cached outside history.
- Text starts Analysis; PDF questions start after ingestion/modals finish, including cancelled or
  failed runs. Sidebar/composer disable while analysis runs. History and four-turn memory survive
  reruns; New chat empties memory by clearing history. Existing model picker remains independent.
- Real spec 01 cards/catalog/settings seams reused; no protected spec 01 source/artifacts edited.

## Verification
Commands use the existing WSL venv, offline guards and stub Analyst/ingestion runners.
- **RED:** new smoke command below produced 3 collection errors before UI modules/fake existed.
- **PASS:** `.venv/bin/python -m pytest -q tests/unit/test_analysis_window.py tests/unit/test_analysis_ui.py tests/functional/test_analysis_flow.py`
  — 10 passed in 25.35 s. Covers state/window, progress, lazy data/history, PDF endings and layouts.
- **PASS:** `.venv/bin/python -m pytest -q` — 734 passed, 2 live tests deselected in 62.99 s.
- **PASS:** `git diff --check -- <iteration-owned tracked files>` — no whitespace errors.

## Deferred to the final iteration (D-118)
- Exhaustive individual checks: VC-201, VC-203 (UI/window), VC-206 (UI), VC-231, VC-232,
  VC-233, VC-234, VC-235. The new smoke cases exercise these contracts together.
- Browser expander interaction, real attachments and 375/1280 px layout (VC-247/NFR-206)
  remain student checks in Iteration 5. AppTest opens Show data through the widget-state seam.
- Final verification also covers cached-frame error handling and every attempt/evidence edge case.

## Files
- **Created:** `ui/analysis.py`, `ui/analysis_window.py`, `tests/unit/test_analysis_ui.py`,
  `tests/unit/test_analysis_window.py`, `tests/functional/test_analysis_flow.py`, this record.
- **Changed:** `app.py`, `ui/chat.py`, `ui/sidebar.py`, `tests/analyst_stubs.py`,
  `tests/functional/conftest.py`, `tests/unit/test_chat.py`, `tests/functional/test_app.py`,
  `tests/functional/test_ingestion_flow.py`, `tests/functional/test_ingestion_verification.py`,
  `specs/02-analyst-plan-artifacts/CONTEXT.md`, `specs/02-analyst-plan-artifacts/DECISIONS.md`.
- **Deleted:** none. Other-agent changes are excluded.

## Decisions and deviations
- S02-D-020: approved UI message/cache contract. S02-D-021: approved chat integration and real
  spec 01 mappings; a chat-side handoff preserves protected ingestion/upload source files.
- The old question-placeholder seam is empty for compatibility. Pre-sidebar handoff ensures busy
  controls are drawn before analysis starts. A PDF+question has separate ingestion/analysis assistant
  messages within the same user turn; old placeholder/count assertions were updated accordingly.
- Initial full run had one superseded exact-expander expectation; it now scopes ingestion card
  assertions around the new Analysis evidence panel. No behavior was removed to make tests pass.

## For the next iteration
- Session `active-analysis` points to the queued/running message. Message fields are
  role/content/kind=analysis/question/thread_id/status/lines/values; `values` is final AnalystState.
- `queue_analysis`, `render_analysis_message`, `status_line`, `is_busy` are in ui/analysis.py;
  `build_window(messages)` is in ui/analysis_window.py; handoff is in ui/chat.py and called by app.py.
- Show data key is `analysis-data-<thread_id>-<table_id>`; frames stay in Streamlit's data cache.
- `StubAnalysisRunner` and `analysis_result` remain in tests/analyst_stubs.py until Iteration 5.
- Consolidate every deferred VC, write live tests/README and move stubs only in Iteration 5.
  Student owns image builds, live/manual checks and commits. Nothing installed or run live here.
- Stop after this iteration for review/commit.

Commit summary: `Feat: Analysis Chat and Evidence (Spec 2)`
