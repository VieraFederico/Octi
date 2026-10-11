# CONTEXT — Spec 01 Ingestion agent (after Iteration 1)

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
- Not yet: table extraction, cleaning, context, prompts, validation, indexing, the graph, the UI
  changes (Iterations 2–11).

## File map
Spec 01 (new or changed this spec):
- `agents/__init__.py`, `agents/ingestion/__init__.py` — package markers (docstring only).
- `agents/ingestion/pdf/__init__.py` — package marker: deterministic PDF reading, no LLM (D-084).
- `agents/ingestion/pdf/document.py` — `open_document`, `pages_without_text`, `is_repeated`,
  `reported_image_pages`; constants `MIN_IMAGE_PAGE_FRACTION`, `MIN_PAGES_FOR_REPETITION`.
- `services/settings.py` — + `INGESTION_MAX_RETRIES`.
- `services/errors.py` — + `DocumentError` leaves, `TableStoreError` (tree in the module docstring).
- `.env.example` — + "Ingestion agent" section with `INGESTION_MAX_RETRIES`.
- `tests/pdf_fixtures.py` — fixture PDF builders (plain module, like `tests/stubs.py`).
- `tests/unit/test_pymupdf_assumptions.py` — A-101, A-102.
- `tests/unit/test_document.py` — `pdf/document.py` (VC-105 … VC-107 function level, VC-123 page
  part, VC-125, VC-169 image part). Not to be confused with `test_documents.py` (sidebar UI).
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
- Repetition rule (also for running text in Iteration 4, FR-124): `is_repeated(pages_with_it, page_count)`
  → `agents/ingestion/pdf/document.py`.
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
.venv/bin/python -m pytest -q                                   # offline suite, ~25 s (224 passed, 1 deselected)
.venv/bin/python -m pytest -q tests/unit/test_document.py       # one module
.venv/bin/python -m pytest -q tests/unit/test_pymupdf_assumptions.py   # A-101 / A-102
# student only (real .env / services):
pytest -m live
python -m scripts.setup_index
python -m scripts.check_services
streamlit run app.py
```

## Known gaps
- VC-105 … VC-107 are checked at function level only; "zero LLM/embedding calls, nothing written"
  (FR-108) is checked at graph level in Iteration 7.
- `open_document` translates only open failures. A PDF that opens but whose page content is damaged
  could make `page.get_text()` raise a raw PyMuPDF error; not seen in tests, not handled yet.
- Fixture tables are ruled (bordered) only; borderless tables are a known limitation of D-046.
- PyMuPDF 1.28.2 prints "Consider using the pymupdf_layout package…" to stdout on the first
  `find_tables()` call in a process; harmless (pytest captures it).
- From spec 00: AppTest cannot attach files to the composer (S00-D-018); `Settings` defaults are not
  exported to the environment (A-006, tracing must stay on when a variable is omitted — FR-154).
