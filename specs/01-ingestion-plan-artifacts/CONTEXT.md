# CONTEXT — Spec 01 Ingestion implementation and final verification

This is the current codebase handoff. The spec and plan remain the authority; implementation
choices live in this directory's DECISIONS.md. Staged verification (D-118) applies.

## Current state
- Foundation: typed settings, error families, redacting logging, service factories, startup checks,
  Streamlit shell, model picker, New chat modal, offline pytest guards. Spec 02 is being implemented
  concurrently; its startup sandbox check is now part of the shared shell.
- Iterations 1–3: PDF opening and unreadable/image detection, geometric table extraction, multi-page
  joins, header flattening, numeric cleaning, contextual text, and deterministic sample PDFs.
- Iteration 4: frozen enrichment prompt, structured models, deterministic validation, embedding
  text and flat records, Parquet storage, catalog decoding, safe write order and rollback.
- Iteration 5: the ingestion graph, validation retry loop, unreadable/skipped pauses, light state,
  per-run data store, in-memory checkpointer, tracing labels and settings-controlled tracing scope.
- Iteration 6: PDF submission starts ingestion after catalog checks. A structured assistant message
  streams status, pauses with buttons, and retains cards, skipped parts, image notes and the later
  question placeholder. Both upload modals are implemented. The Library and sidebar use the session
  catalog, and Document controls navigate to the filtered Library. Busy controls disable before
  streaming; New chat at a pause closes the run's data store and discards the runtime.
- Catalog loads once per session; an upload retries a failed load before any run. An indexed result
  updates the session catalog directly. A cleanup warning keeps possible old-version leftovers.
- Iteration 7: deferred graph and UI verification tests are implemented, including both upload
  modals, all pause choices, summaries/history, busy controls, catalog recovery and checkpoint limits.
  The graph declares its specified conditional destinations so its Mermaid export is complete.
  README documents usage, design choices, the exported workflow, sample regeneration and limitations.
- `verification.md` maps all 82 active requirements and named test evidence. The isolated live
  ingestion test is prepared; the student has not run live/browser/performance checks (VC-164/166).
  Full offline suite is green: 724 passed, 2 deselected in 60.29 s. The under-60-second target
  (NFR-103) was missed by 0.29 s and remains unconfirmed. Final acceptance awaits those checks.

## File map
Ingestion implementation:
- agents/ingestion/schemas.py — ExtractedTable, TableContext, enrichment/metadata models, CatalogEntry.
- agents/ingestion/pdf/document.py — opening, no-text pages, significant images and repetition.
- agents/ingestion/pdf/cleaning.py — header flattening, numeric parsing, row labels, dtype/text helpers.
- agents/ingestion/pdf/tables.py — SHA/id helpers, header clues, filtering, joining and extraction.
- agents/ingestion/pdf/context.py — geometric and font-based Table context, bounded in characters.
- agents/ingestion/prompts.py — frozen system prompt, two examples and retry-aware messages.
- agents/ingestion/validation.py — five deterministic checks producing feedback sentences.
- agents/ingestion/indexing.py — metadata/record builders, size guard, embedding text, catalog decoding,
  write_document, TableToIndex and WriteResult.
- agents/ingestion/state.py — light state/result/pause shapes, RunStore, IngestionDeps and make_deps.
- agents/ingestion/nodes.py — nine graph nodes, format_pages, safe outcome sentences.
- agents/ingestion/graph.py — routers, build_graph, run/resume, computed limit and tracing scope.
- services/table_store.py — atomic Parquet writes, exact dtype reads, deletion and id validation.
- services/vector_store.py — index factories/checks, paginated list/fetch/version lookup and mutations.
- scripts/make_sample_pdfs.py — deterministic sample generator and importable evaluation constants.
- data/sample_pdfs/acme-annual-report-2023.pdf, informe-regional-2024.pdf — generated committed PDFs.
- data/tables/ — ignored Parquet Table store; uploaded PDFs are never saved.

Iteration 6 UI:
- ui/catalog.py — session load/failure flags, result updates, grouping/lookups and Library navigation.
- ui/upload.py — pending-upload processing, hash-first decisions and both confirmation modals.
- ui/ingestion.py — active run/runtime, streaming presentation, run history, pause/resume and abandon.
- ui/table_card.py — shared escaped expandable card with a scrolling preview.
- ui/chat.py — in-memory attachment extraction, pending upload and structured message rendering.
- ui/documents.py — session Document previews, native HTML expanders, local v2 navigation component.
- ui/library.py — newest-first grouping, non-typeable Document filter and shared cards.
- ui/sidebar.py — navigation, streaming disablement and session Documents.
- ui/new_chat.py — erase/cancel warning policy, including paused-run cleanup.
- app.py — startup, session catalog, pending upload, sidebar/dialogs and selected view.
- assets/styles.css — existing theme/layout and Document button styling.
- ui/startup.py, ui/error_screen.py — owned by the concurrent spec 02 work; not edited by Iteration 6.

Tests:
- tests/conftest.py — offline socket and repository secret-file guards, fake settings, table_store_dir.
- tests/stubs.py — existing model/embedding/index fakes plus catalog_entry and ScriptedIngestionRunner.
- tests/pdf_fixtures.py — in-memory fixture PDFs, including tables, images and encrypted documents.
- tests/unit/test_document.py, test_pymupdf_assumptions.py, test_cleaning.py, test_tables.py,
  test_context.py, test_sample_pdfs.py — deterministic PDF/data coverage from Iterations 1–3.
- tests/unit/test_prompts.py, test_validation.py, test_indexing.py, test_table_store.py,
  test_vector_store.py — prompt, metadata, write order, rollback and storage coverage.
- tests/unit/test_state.py, test_nodes.py, test_graph.py, test_graph_routing.py,
  test_tracing_config.py — graph, routes, pauses and trace configuration.
- tests/unit/test_catalog_ui.py, test_upload.py, test_table_card.py, test_ingestion_ui.py — new smoke tests.
- tests/unit/test_chat.py, test_documents.py, test_new_chat.py — chat and existing sidebar/modal checks.
- tests/functional/test_ingestion_flow.py, test_library.py — new offline AppTest smoke flows.
- tests/unit/test_ingestion_final_graph.py — deferred refusal, oversize, checkpoint, outage and export checks.
- tests/functional/test_ingestion_verification.py — complete deferred upload/catalog/run UI scenarios.
- tests/unit/test_readme.py — product documentation and exact compiled Mermaid export checks.
- tests/live/test_ingestion_live.py — student-run real ingestion shape check in isolated storage (S01-D-025).
- README.md — shipped product usage, setup, architecture, design choices, graph and known limitations.
- specs/01-ingestion-plan-artifacts/verification.md — every requirement/VC and its named test evidence.
- tests/functional/conftest.py — fake catalog and ready sandbox factory; failure tests can override it.
- Existing functional shell/modal/error-screen tests remain regression checks.
- tests/analyst_stubs.py and spec 02 files belong to the concurrent implementation, not this iteration.

## Public interfaces
PDF and data:
- open_document(data) -> pymupdf.Document; pages_without_text, reported_image_pages -> list[int].
- document_sha(data), make_table_id(sha, page, position), extract_tables(doc, sha).
- flatten_headers(header_rows, spans, column_spans), clean_column(values), build_dataframe(names, rows),
  row_headers(frame), dtype_name(series), rows_as_text(frame, limit, max_cell=None).
- collect_context(doc, table) -> TableContext(section, caption, before, after, footnotes).
- ExtractedTable carries id/pages/parts/columns/frame/hints/row_headers/unreadable (schemas.py).

Enrichment and storage:
- build_messages(table, context, source_file, previous=None, feedback=()) -> messages (prompts.py).
- validate(answer: TableEnrichment | dict, table) -> feedback sentences (validation.py).
- assemble_metadata(enrichment, table, source_file), index_metadata(metadata, table, document_sha,
  ingested_at=None), exceeds_size_guard, embedding_text, entry_from_record (indexing.py).
- write_document(settings, source_file, document_sha, tables, *, embeddings, index) ->
  WriteResult(table_ids, previous_removed); load_catalog(settings, index=None) -> list[CatalogEntry].
- CatalogEntry includes at most 50 row_headers, row_headers_total, timezone-aware ingested_at,
  document_sha, preview, n_rows and n_cols, in addition to TableMetadata (D-116).
- read_table(table_id) -> DataFrame, write_table(table_id, frame), delete_tables(ids) (table_store.py).
- open_index, list_records, find_versions (fetch_by_metadata), upsert_records and delete_records
  take the namespace explicitly (vector_store.py).

Graph:
- deps = make_deps(settings); graph = build_graph(deps), kept together for the session.
- run_ingestion(graph, deps, source_file, pdf, thread_id=None, on_update=None) -> RunResult.
- resume_ingestion(graph, deps, thread_id, continue/index/cancel, on_update=None) -> RunResult.
- RunResult: thread_id, status paused/finished, question and values. PauseQuestion: pause, intro,
  bullets, question and choices (value/label). on_update(node, partial_update) receives node updates.
- Finished values contain outcome, assembled[i].record_metadata, skipped and image_pages.
- IngestionDeps holds settings, embeddings, index, chat factory and runs; RunStore open/get/close.

UI/session contract:
- catalog, catalog-loaded, catalog-attempted — cached entries and load state (ui/catalog.py).
- ingestion-settings — startup's typed settings; no settings values enter the message history.
- ensure_catalog(state, settings, loader=None, retry=False), update_catalog(state, entries,
  previous_removed=), documents(state), by_hash, by_name, open_library(state, name).
- library-filter — Document dropdown; view = Chat/Library. open_library sets both (ui/catalog.py).
- pending-upload — {name, pdf, text, announced?}; bytes only in memory (ui/upload.py).
- upload-confirming — identical/replace decision. process_pending_upload runs before sidebar rendering;
  render_upload_dialog draws the persistent modal with Keep/Open or Cancel/Replace.
- active-ingestion — reference to the structured assistant message; ingestion-runtime = (graph, deps).
- ingestion-pdf — queued bytes, removed before run_ingestion transfers them into RunStore.
- queue_run, is_busy, is_streaming, abandon_run, status_line, render_run_message (ui/ingestion.py).
- Run message: role/content/kind=ingestion/thread_id/source_file/status/lines/entries/skipped/
  image_pages/question/text; progress only while active; resume only after a pause choice.
  entries are CatalogEntry objects; the message holds no PDF bytes or full DataFrames.
- render_table_card(entry), table_card_html(entry) (ui/table_card.py).
- load_documents, documents_html(..., navigable=False, disabled=False), render_documents(disabled=)
  (ui/documents.py). The local component emits only a validated file name; details stay in the browser.
- ScriptedIngestionRunner(results, steps=None): one RunResult per start/resume, optional per-call
  [(node, update), ...] steps, calls log and a local RunStore (tests/stubs.py).

Sample data (scripts/make_sample_pdfs.py):
- ACME_YEARS (2021–2023); ACME_INCOME/ACME_INCOME_COLUMNS, ACME_RD/ACME_RD_COLUMNS,
  ACME_REGIONAL_NET_SALES, ACME_MARKET_SHARE/ACME_MARKET_SHARE_YEARS,
  ACME_HEADCOUNT/ACME_HEADCOUNT_COLUMNS, ACME_MONTHLY.
- Informe sample: INFORME_YEARS, INFORME_POPULATION, INFORME_LABOUR/INFORME_LABOUR_COLUMNS.
- ACME_FILE, INFORME_FILE, build_acme_pdf, build_informe_pdf, write_sample_pdfs(out_dir=OUT_DIR).
- Regional sales sum to net revenue; monthly sales sum to net revenue ×1000. Regions: Patagonia,
  Cuyo, Pampa, NOA, NEA, with no national row. ACME has five Tables; Informe has two.

## Conventions & invariants
- Never read secret files, install/download, commit/push, or edit the protected root/spec documents.
- Decisions not already settled require the student; spec-local accepted choices use S01-D-NNN.
- Offline tests only: stubs, fake settings, network guard. Live/manual checks belong to the student.
- TDD, Given/When/Then and smoke coverage during feature iterations; remaining VCs go to Iteration 7
  under staged verification (D-118). Each iteration's full offline suite must be green.
- User-visible chat/Library/sidebar messages do not name backend services or expose raw failures.
- PDF text is untrusted data: escaped in UI HTML, fenced/neutralized in prompts; feedback is not UI text.
- LLM output supplies meaning only; ids, names of columns, dtypes, pages and row labels come from code.
- Graph state is light (at most 20 rows per Table); bytes/documents/frames are only in RunStore.
- Pauses keep the store; finish, failure or abandoned conversation closes it. New chat also drops
  the runtime/checkpointer. Browser refresh loses a paused run by design.
- The composer and model picker are disabled while active. Sidebar navigation/Document buttons are
  disabled while streaming and enabled at pauses. Controls are rendered before the blocking call.
- Catalog load failure is remembered, with generic Library/sidebar text. PDF submission retries first.
- A successful run updates from its own results, never a post-run catalog reload (eventual consistency).
- Safe writes: same-name lookup, embeddings, atomic Parquet, batched upsert, old records then files.
  Rollback removes only new ids; an old same-byte version is never deleted on a failed write.
- read_table restores object text columns and None gaps. Table ids containing separators are refused.
- Row headers: 50 stored, 10 on cards, full count separately. Preview: five pipe-delimited rows,
  40 characters per cell, total 2,000; wide text scrolls inside its own box.
- Pure extraction uses 1-based pages and geometric cell spans; ambiguous 1.234 uses English style.
  Whole numeric values outside signed int64 stay text; a column converts all-or-nothing.
- Services remain agent-agnostic; graph/meaning logic remains inside agents/ingestion (D-084).
- Code/docs use neutral English. Keep LF line endings (D-044). Verification records stay separate
  from the product README.

## Commands
From PowerShell, use the existing WSL virtual environment (no installation):
- wsl .venv/bin/python -m pytest -q — full offline suite.
- wsl .venv/bin/python -m pytest -q tests/unit/test_catalog_ui.py tests/unit/test_upload.py
  tests/unit/test_table_card.py tests/unit/test_ingestion_ui.py tests/functional/test_ingestion_flow.py
  tests/functional/test_library.py — Iteration 6 smoke tests (one command, join the lines).
- .venv/bin/python -m scripts.make_sample_pdfs — regenerate committed samples (offline, student owns).
- Live tests and the real app are run by the student only.

## Known gaps
- Final tests now implement the deferred lists from Iterations 5 and 6 (D-118); verification.md
  records executed evidence and the remaining live/manual checks without marking them passed.
- Browser clicks in the local component, real attachments and 375/1280 px layout checks are manual
  student checks in Iteration 7; AppTest cannot attach PDFs or execute component JavaScript.
- Step-4 cleanup warnings retain possible old entries in the session; successful re-upload cleans up.
- Context is re-read per Table. PyMuPDF external headers and borderless/scanned/image tables remain
  known limitations; line-end hyphenation leaves a space. The damaged-text fixture patches extraction.
- ingested_at is stamped per Table at assembly. load_catalog assumes valid Octi records.
- A Table with exceptionally large cells can exceed the prompt character budget; no runtime cap exists.
- Real fetch_by_metadata support, structured output and trace grouping are confirmed by live checks.
- Concurrent spec 02 changes can temporarily break the shared full suite; never change its files to
  hide such a failure. Report the cause and wait for its owning agent/student if unresolved.
