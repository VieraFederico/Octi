# CONTEXT — Spec 01 Ingestion agent (after Iteration 3)

Starting point: spec 00 complete (`specs/00-foundation-plan-artifacts/CONTEXT.md`, capsule
`specs/00-foundation-frozen.md`). This file describes the codebase as it stands now.

## Current state
- Spec 00 foundation unchanged in behaviour: typed `Settings` (fail-fast, names only), error tree,
  redacting logging, LiteLLM / Pinecone / LangSmith factories, the two CLIs, the Streamlit shell
  (chat with placeholder replies, PDF-only composer, empty Library and Documents), the error screen,
  the offline pytest harness and one live smoke test.
- Spec 01, Iteration 1 done:
  - `Settings.INGESTION_MAX_RETRIES` (int 0–5, default 2; FR-155), documented in `.env.example`.
  - Error tree: `DocumentError` group (`DocumentUnreadableError`, `DocumentEncryptedError`,
    `DocumentWithoutTextError`, each carrying its fixed FR-105 … FR-107 sentence) and
    `TableStoreError` directly under `AppError`.
  - `agents/ingestion/pdf/document.py`: open PDF bytes or refuse them (FR-105 … FR-107), list pages
    without selectable text (FR-119 page part), list pages whose images the summary must mention
    (FR-121, 2 % area rule + repetition rule from 3 pages).
  - `tests/pdf_fixtures.py`: in-memory fixture PDF builders (HTML through PyMuPDF's Story; S01-D-001).
  - A-101 and A-102 proven (`tests/unit/test_pymupdf_assumptions.py`).
- Spec 01, Iteration 2 done: pure cell cleaning in `pdf/cleaning.py` — flatten marked headers using
  horizontal spans; convert numeric columns all-or-nothing with percent/currency hints; build a
  DataFrame and collect first-column row labels. Original text is preserved on failed conversion.
  Whole columns outside signed int64 range stay text (student-approved S01-D-007).
- Spec 01, Iteration 3 done (spec v0.8):
  - `pdf/tables.py`: every table PyMuPDF finds, then: fake tables dropped (DEBUG log), unreadable
    tables flagged without data, header rows detected by clue (S01-D-008), tables continued on the
    next page joined, then cleaned with `pdf/cleaning.py`. Returns `ExtractedTable`s.
  - `pdf/context.py`: the five-field `TableContext` per Table by position and font (FR-123 … 126;
    overlap rule S01-D-011).
  - `scripts/make_sample_pdfs.py` writes the two committed sample PDFs from module-level constants
    (D-070, D-107, S01-D-013); `data/tables/` is git-ignored.
- Not yet: prompts, validation, records, Table store, Pinecone writes, the graph, the UI changes
  (Iterations 4–7).

## File map
Spec 01 (new or changed this spec):
- `agents/__init__.py`, `agents/ingestion/__init__.py` — package markers (docstring only).
- `agents/ingestion/pdf/__init__.py` — package marker: deterministic PDF reading, no LLM (D-084).
- `agents/ingestion/pdf/document.py` — `open_document`, `pages_without_text`, `is_repeated`,
  `reported_image_pages`; constants `MIN_IMAGE_PAGE_FRACTION`, `MIN_PAGES_FOR_REPETITION`.
- `agents/ingestion/pdf/cleaning.py` — `flatten_headers`, `clean_column`, `build_dataframe`,
  `row_headers`; deterministic cells-to-data conversion, no PDF or external I/O.
- `agents/ingestion/pdf/tables.py` — `document_sha`, `make_table_id`, `extract_tables`; constants
  `MAX_HEADER_ROWS`, `YEAR_RANGE`, `UNREADABLE_SHARE`, `MERGE_TOLERANCE`.
- `agents/ingestion/pdf/context.py` — `collect_context`; constants `MAX_PARAGRAPH_CHARS` (600),
  `MAX_CONTEXT_CHARS` (2,000), `MAX_CAPTION_FALLBACK_LINES`, `MAX_HEADING_WORDS`, `LARGER_FONT`.
- `agents/ingestion/schemas.py` — `ExtractedTable`, `TableContext` (plain dataclasses; the §7
  Pydantic models join in Iteration 4), type alias `Box`.
- `scripts/make_sample_pdfs.py` — sample PDF generator and the table-data constants.
- `data/sample_pdfs/acme-annual-report-2023.pdf`, `data/sample_pdfs/informe-regional-2024.pdf` —
  committed, generated (byte-identical on re-run with PyMuPDF 1.28.2).
- `.gitignore` — + `data/tables/`.
- `services/settings.py` — + `INGESTION_MAX_RETRIES`.
- `services/errors.py` — + `DocumentError` leaves, `TableStoreError` (tree in the module docstring).
- `.env.example` — + "Ingestion agent" section with `INGESTION_MAX_RETRIES`.
- `tests/pdf_fixtures.py` — fixture PDF builders (plain module, like `tests/stubs.py`).
- `tests/unit/test_pymupdf_assumptions.py` — A-101, A-102.
- `tests/unit/test_document.py` — `pdf/document.py` (VC-105 … VC-107 function level, VC-123 page
  part, VC-125, VC-169 image part). Not to be confused with `test_documents.py` (sidebar UI).
- `tests/unit/test_cleaning.py` — VC-112/114/115 grid part, VC-117 … VC-121, VC-122 hints;
  decimal-style, missing, original-text and signed-int64-boundary regressions (60 cases).
- `tests/unit/test_tables.py` — VC-108 … VC-114, VC-116, VC-123 table part (21 cases).
- `tests/unit/test_sample_pdfs.py` — VC-161: repeatable output, committed = fresh, every table's
  values equal the constants, constants consistent (12 cases).
- `tests/unit/test_context.py` — VC-126 … VC-129, VC-169 context part, sample captions (17 cases).
- `tests/unit/test_settings.py`, `tests/unit/test_errors.py` — extended (VC-158, VC-011).

Spec 00 (unchanged):
- `services/logging_setup.py`, `services/llm.py`, `services/vector_store.py`, `services/tracing.py`,
  `services/health.py` — logging, LiteLLM, Pinecone, LangSmith, service checks.
- `scripts/setup_index.py`, `scripts/check_services.py` — thin CLIs.
- `app.py` and `ui/` — Streamlit entry and views (`chat.py`, `sidebar.py`, `documents.py` with the
  `load_documents()` seam, `library.py` empty state, `new_chat.py`, `error_screen.py`, `bubble.py`,
  `logo.py`, `style.py`, `icons.py`, `startup.py`).
- `tests/conftest.py` (autouse network and `.env` guards; `fake_env`, `make_settings`),
  `tests/stubs.py`, `tests/unit/`, `tests/functional/` (AppTest), `tests/live/test_smoke.py`.
- `README.md`, `requirements.txt` (spec 01 deps pinned: langgraph 1.2.14, pandas 3.0.6,
  pyarrow 25.0.1, pymupdf 1.28.2), `pytest.ini`, `.gitattributes` (LF everywhere, D-044).

## Public interfaces (owner → read the code there; SPEC §7 is the contract)
Spec 01:
- Retry limit: `Settings.INGESTION_MAX_RETRIES` → `services/settings.py`.
- Document errors: `DocumentError` + three leaves (no-argument constructors, fixed `message`),
  `TableStoreError(user_message)` → `services/errors.py`.
- Open a PDF: `open_document(data: bytes) -> pymupdf.Document` (caller closes it) →
  `agents/ingestion/pdf/document.py`.
- Pages without text: `pages_without_text(doc) -> list[int]` (1-based) → `agents/ingestion/pdf/document.py`.
- Image notes: `reported_image_pages(doc) -> list[int]` (1-based, sorted) → `agents/ingestion/pdf/document.py`.
- Repetition rule (images, and running text in `pdf/context.py`, FR-124): `is_repeated(pages_with_it, page_count)`
  → `agents/ingestion/pdf/document.py`.
- Marked headers: `flatten_headers(header_rows, spans, column_spans)` → `agents/ingestion/pdf/cleaning.py`.
- Typed column plus hints: `clean_column(values)` → `agents/ingestion/pdf/cleaning.py`.
- DataFrame plus hints by name: `build_dataframe(names, rows)` → `agents/ingestion/pdf/cleaning.py`.
- First-column labels: `row_headers(frame)` → `agents/ingestion/pdf/cleaning.py`.
- Document hash: `document_sha(data) -> str` (full hex) → `agents/ingestion/pdf/tables.py`.
- Ids: `make_table_id(sha, page, position) -> str` → `agents/ingestion/pdf/tables.py`.
- Tables: `extract_tables(doc, sha) -> list[ExtractedTable]`, reading order → `agents/ingestion/pdf/tables.py`.
- Extracted Table: `ExtractedTable(table_id, pages, parts, columns, frame, hints, row_headers,
  unreadable)`; `parts` = `[(page, box)]`; unreadable → `frame None`, no columns → `agents/ingestion/schemas.py`.
- Context: `collect_context(doc, table) -> TableContext(section, caption, before, after, footnotes)`
  → `agents/ingestion/pdf/context.py`, `agents/ingestion/schemas.py`.
- Sample PDFs: `write_sample_pdfs(out_dir=OUT_DIR) -> list[Path]`, `build_acme_pdf()`,
  `build_informe_pdf()`, `ACME_FILE`, `INFORME_FILE` → `scripts/make_sample_pdfs.py`
  (`python -m scripts.make_sample_pdfs`).
- Sample table data (import from `scripts.make_sample_pdfs`; spec 03 derives expected answers):
  - `ACME_YEARS` = (2021, 2022, 2023).
  - `ACME_INCOME[year][column]`, `ACME_INCOME_COLUMNS` = Revenue (gross), Revenue (net), Net income,
    Net margin (USD millions; margin in %). Table 1, page 1.
  - `ACME_RD[year][column]`, `ACME_RD_COLUMNS` = R&D expenses (USD millions), R&D staff. Table 2, page 1.
  - `ACME_REGIONAL_NET_SALES[region][year]` (USD millions; sums to net revenue) and
    `ACME_MARKET_SHARE[region][year]` (%), `ACME_MARKET_SHARE_YEARS` = (2022, 2023); regions
    Patagonia, Cuyo, Pampa, NOA, NEA, no national row. Table 3, page 2.
  - `ACME_HEADCOUNT[department][column]`, `ACME_HEADCOUNT_COLUMNS` = Employees 2022, Employees 2023,
    Change (%; `None` = n/a). Table 4, page 3 (right column).
  - `ACME_MONTHLY["YYYY-MM"][column]` = Net sales (USD thousands), Change vs previous month (%);
    each year sums to net revenue × 1000. Table 5, pages 4–5.
  - `INFORME_YEARS` = (2022, 2023); `INFORME_POPULATION[region][year]` (thousands) — Cuadro 1;
    `INFORME_LABOUR[region][column]`, `INFORME_LABOUR_COLUMNS` = Tasa de desempleo, Tasa de empleo
    (%) — Cuadro 2.
- Test fixtures: `Page(blocks, images)`, `make_pdf(*pages) -> bytes`, `heading`, `paragraph`,
  `table(header, rows, merged_header=...)`, `Image(rect, shade)`, `image_covering(fraction, shade=)`,
  `image_only_page(shade=)`, `text_page(text, *images)`, `encrypt(pdf, user_password=)`, constants
  `PAGE_RECT`, `MARGIN`, `CONTENT_RECT`, `CSS` → `tests/pdf_fixtures.py`.
Spec 00 (unchanged):
- Configuration: `get_settings()`, `Settings.from_mapping()` → `services/settings.py`.
- Logging: `configure_logging(settings)` → `services/logging_setup.py`.
- Models: `make_chat_model`, `make_embeddings`, `list_proxy_models`, `translate_proxy_errors` → `services/llm.py`.
- Tracing client: `make_langsmith_client`, `translate_tracing_errors` → `services/tracing.py`.
- Index: `check_index` → `IndexStatus`, `ensure_index`, `make_pinecone_client` → `services/vector_store.py`.
- Service check: `run_checks(load_settings, clients)`, `Clients` → `services/health.py`.
- App start-up: `load_startup()` → `Startup` → `ui/startup.py`; conversation in session key `messages`
  → `ui/chat.py`; sidebar Documents seam `load_documents()` → `ui/documents.py`; Library view
  `render_library()` → `ui/library.py`.

## Conventions & invariants
- Raise only leaf errors; chain library errors with `from exc`; show only `user_message` to users.
- `DocumentError` leaves are raised with no argument (`raise DocumentEncryptedError()`); their sentence
  is the spec's, verbatim (S01-D-004).
- PyMuPDF documents are never wrapped (D-084); whoever calls `open_document` closes the document
  (`with open_document(data) as doc:`). The PDF bytes are never written to disk (FR-101).
- Page numbers in every public result are 1-based (`page.number + 1`).
- Cleaning helper contracts are S01-D-006. Header spans are `(x0, x1)` or `None`, aligned with
  rectangular marked header rows; `column_spans` supplies each column's horizontal extent.
  Header-row detection belongs to Iteration 3, not `flatten_headers`.
- A cleaned column is an `int64` / `float64` Series, or an object Series preserving original text
  and missing markers; metadata later calls the latter dtype `text`. Numeric hints are distinct
  first-seen strings. The builder returns hints for every column name, including empty lists.
- Decimal style is chosen across the column before strict separator parsing; an incompatible cell
  keeps the whole column text with no hints (FR-116/117). Percent values keep their written scale.
  `Decimal` preserves whole-number precision before conversion. Only columns requiring int64 are
  range-checked (S01-D-007); gaps/fractions still use the required float64 dtype.
- Row headers examine only the first column, omit FR-115 missing markers, retain original labels
  and leave the first column in the DataFrame.
- Extraction pipeline per table: `< 2 columns` → drop; unreadable → flag; header clues (S01-D-008)
  → `no data row` / `no filled data cell` → drop; join; flatten the first part's header; clean.
  `flatten_headers` gets `(x0, x1)` spans, never full boxes.
- Positions count every table PyMuPDF finds on a page, dropped ones included (S01-D-009).
- Context blocks: outside every table box, not running text (`is_repeated`), not a bare page number,
  overlapping the Table by half the narrower width (S01-D-011); MuPDF blocks are split by column;
  ligatures expanded (S01-D-012).
- Sample PDFs are drawn from the script's constants only; change the data there, regenerate, commit
  both PDFs.
- Spec §7 code constants live as named module constants next to the code that uses them.
- `pymupdf.open(stream=..., filetype="pdf")` raises `pymupdf.FileDataError` (also for empty bytes,
  via its subclass `EmptyFileError`) — the only exception `open_document` translates.
- One module per external service holds its client factory and error translation (D-034); services
  never import agents (D-084).
- Never read `os.environ` outside `services/settings.py` (lint test).
- Tests: offline; Given/When/Then comments; the VC id in each docstring; stubs from `tests/stubs.py`,
  fixture PDFs from `tests/pdf_fixtures.py` (built in memory per test, nothing binary committed);
  pytest fixtures by parameter name; no test imports another test module.
- Keep the repo LF (`.gitattributes`); files edited from the Windows side may come back CRLF.
- Course reuse is credited by title in README › Credits, never by `sources/` path.

## Commands
```bash
.venv/bin/python -m pytest -q                                   # offline suite, ~35 s (334 passed, 1 deselected)
.venv/bin/python -m pytest -q tests/unit/test_tables.py tests/unit/test_sample_pdfs.py tests/unit/test_context.py
.venv/bin/python -m scripts.make_sample_pdfs                     # regenerate data/sample_pdfs/ (offline)
.venv/bin/python -m pytest -q tests/unit/test_cleaning.py        # 60 cases, pure cells-to-data
.venv/bin/python -m pytest -q tests/unit/test_document.py       # one module
.venv/bin/python -m pytest -q tests/unit/test_pymupdf_assumptions.py   # A-101 / A-102
# student only (real .env / services):
pytest -m live
python -m scripts.setup_index
python -m scripts.check_services
streamlit run app.py
```

## Known gaps
- VC-122 checks hints at extraction; prompt rendering is Iteration 4.
- VC-123's `�` cells are simulated (S01-D-010); the graph-level pause is Iteration 5.
- PyMuPDF's "external" header (text above a borderless table) is ignored (S01-D-008).
- A word hyphenated at a line end keeps a space in context text (`full- time`); not dehyphenated.
- `collect_context` re-reads the page layout (and `find_tables`) on each call.
- Spec FR-124's wording must follow S01-D-011 (spec tab).
- Cleaning inputs are rectangular/aligned grids from extraction; these helpers do not validate
  malformed caller shapes. Ambiguous `1.234` defaults to English (D-055, documented limitation).
- VC-105 … VC-107 are checked at function level only; "zero LLM/embedding calls, nothing written"
  (FR-108) is checked at graph level in Iteration 7.
- `open_document` translates only open failures. A PDF that opens but whose page content is damaged
  could make `page.get_text()` raise a raw PyMuPDF error; not seen in tests, not handled yet.
- Fixture tables are ruled (bordered) only; borderless tables are a known limitation of D-046.
- PyMuPDF 1.28.2 prints "Consider using the pymupdf_layout package…" to stdout on the first
  `find_tables()` call in a process; harmless (pytest captures it).
- From spec 00: AppTest cannot attach files to the composer (S00-D-018); `Settings` defaults are not
  exported to the environment (A-006, tracing must stay on when a variable is omitted — FR-154).
