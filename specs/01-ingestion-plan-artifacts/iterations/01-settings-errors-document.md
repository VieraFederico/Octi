# Iteration 01 — Settings, errors, PDF fixtures and reading the document

Commit SHA: (filled by student). Previous commit (the plan): `f476b80`.

## Criteria
| Criterion | Command | Result |
|---|---|---|
| VC-158: unset → 2, `5` → 5, `6` / `-1` / `two` → error naming `INGESTION_MAX_RETRIES`; `.env.example` has it | `.venv/bin/python -m pytest -q tests/unit/test_settings.py` | PASS — 23 passed (5 new). RED first: 5 failed |
| VC-011 (spec 00) with the new leaves; each leaf has its user message | `.venv/bin/python -m pytest -q tests/unit/test_errors.py` | PASS — 21 passed (4 leaves added to the tree table, 3 exact-sentence tests, 1 `TableStoreError` placement test). RED first: collection `AttributeError` |
| A-101 and A-102 | `.venv/bin/python -m pytest -q tests/unit/test_pymupdf_assumptions.py` | PASS — 2 passed. RED first: `ModuleNotFoundError: tests.pdf_fixtures` |
| VC-105, VC-106, VC-107 (function level) | `.venv/bin/python -m pytest -q tests/unit/test_document.py` | PASS — `not a pdf`, empty bytes and a PNG → FR-105 sentence; user-password PDF → FR-106; image-only PDF → FR-107 |
| VC-123 (page part): pages 2–3 image-only of 4 → `[2, 3]` | same file | PASS |
| VC-125: large image on page 5 + small logo on every page → `[5]` | same file | PASS |
| VC-169 (image part): 1-page PDF with one large image → `[1]`; 4 pages with the same large image → `[]` | same file | PASS (17 passed in the file; RED first: `ModuleNotFoundError: agents`) |
| Full suite green | `.venv/bin/python -m pytest -q` | PASS — 224 passed, 1 deselected in 24.1 s (baseline 192) |

Mutation check (by hand, not committed): disabling the repetition rule, lowering the 3-page minimum,
lowering the 2 % threshold or breaking `pages_without_text` each made at least one document test fail.

## Raw A-101 / A-102 observation (PyMuPDF 1.28.2, Story HTML table with `colspan`)
`extract()` → `[['Region', 'Revenue', None, ''], ['', '2023', '2024', 'Total'], ['North', '10', '12', '22'], …]`;
`header.names` → `['Region', 'Revenue', None, '']`; row 0 cell boxes → `[box, box spanning x 93.4–163.9
(two columns), None, box]`; every other cell, empty or not, has its own box.

## Files
Added: `agents/__init__.py`, `agents/ingestion/__init__.py`, `agents/ingestion/pdf/__init__.py`,
`agents/ingestion/pdf/document.py`, `tests/pdf_fixtures.py`, `tests/unit/test_pymupdf_assumptions.py`,
`tests/unit/test_document.py`, `specs/01-ingestion-plan-artifacts/CONTEXT.md`, `…/DECISIONS.md`, this record.
Changed: `services/settings.py`, `services/errors.py`, `.env.example`, `tests/unit/test_settings.py`,
`tests/unit/test_errors.py`.
Deleted: none.

## Decisions
S01-D-001 (Story HTML fixtures; A-102 holds), S01-D-002 (non-PDF content is unreadable),
S01-D-003 (images identified by content hash), S01-D-004 (document leaves carry their sentence),
S01-D-005 (no-text test and image-note scope). S01-D-002, -003 and -004 were flagged for the
student's confirmation and accepted (2026-10-11, after commit `08a5171`).

## Deviations
- `open_document` also refuses content MuPDF opens but that is not a PDF (a renamed PNG), with the
  FR-105 sentence (S01-D-002): the spec says "a file PyMuPDF cannot open", and PyMuPDF does open it.
- Added a public `is_repeated(pages_with_it, page_count)` helper beyond the three named functions, so
  Iteration 4 (running text, FR-124) reuses the same repetition rule instead of re-implementing it.
- Fixture helpers beyond the plan's list: `heading`, `paragraph`, `text_page`, `image_covering`
  (named by the rule they test). `table(header=())` allows a headerless table for Iteration 3.

## Gotchas
- `pymupdf.open(..., filetype="pdf")` does not force PDF parsing: MuPDF sniffs the content, so a PNG
  opens as a 1-page document. Check `doc.is_pdf`.
- Every open failure arrives as `pymupdf.FileDataError` ("Failed to open stream"); empty bytes as
  its subclass `EmptyFileError`.
- `doc.is_encrypted` is `False` after an owner-password-only PDF auto-authenticates; `needs_pass` is
  the right test for "a password is required".
- PyMuPDF de-duplicates identical images on insert (same xref on every page), so fixtures cannot
  show the xref-vs-digest difference; the digest is still the robust choice (S01-D-003).
- `insert_htmlbox(..., scale_low=1)` returns `spare_height = -1` when the HTML does not fit; the
  default would silently shrink the text.
- The Edit tool wrote CRLF into `services/settings.py` and `tests/unit/test_settings.py` (converted
  back to LF) and into `.env.example` (left as is: the shell guard forbids naming that file, and
  `.gitattributes` converts it to LF on `git add`).
- First `find_tables()` per process prints a `pymupdf_layout` suggestion to stdout; harmless.

## For the next iteration
- Iteration 2 is pure functions (no PDF). Use A-101's shape as the input contract for header rows:
  `None` = position covered by a merge, `""` = empty cell, and each real cell's box (x0, x1) tells
  whether the cell to the left spans the covered position.
- Iteration 3: build table fixtures with `table(header, rows, merged_header=...)` inside
  `Page(blocks=...)`; one `Page` is exactly one PDF page; bold comes from `<th>` cells.
- Iteration 4: reuse `is_repeated` from `pdf/document.py` for FR-124's running text.
- Iteration 7: FR-119 bullets from `pages_without_text`, the FR-121 note from
  `reported_image_pages`; close the document in the per-run store when the run ends.
