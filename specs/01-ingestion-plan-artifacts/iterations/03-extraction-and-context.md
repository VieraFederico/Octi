# Iteration 03 — Extracting Tables from PDFs, the sample PDFs and the Table context

Commit SHA: (filled by student). Previous commit (Iteration 2): `4ab3689`.
Spec version read before implementation: **0.8** (D-107: FR-156 and VC-161 extended).

## Criteria
| Criterion | Command | Result |
|---|---|---|
| VC-108: two tables → positions 1, 2; ids `…-p1-t1`, `…-p1-t2` | `.venv/bin/python -m pytest -q tests/unit/test_tables.py` | PASS |
| VC-109: 1-column box, header-only, sparse 3×3 → only the sparse kept; DEBUG log | same | PASS. PyMuPDF never reports the 1-column box (S01-D-010) |
| VC-110: 30 rows over pages 2–3, header repeated or not → one Table, pages [2, 3]; 3-page chain | same | PASS |
| VC-111: different header / different column count → two Tables | same | PASS (+ "only the last table of a page continues") |
| VC-112, VC-114 at PDF level | same | PASS (merged header, `$` hint, row headers; empty cell → `Column 3`) |
| VC-113: bold `Q1 \| 1 \| 2 \| 3` → header; plain → data | same | PASS |
| VC-116: four candidate header rows → 3; all header-looking → 1 data row kept | same | PASS (+ year-row case) |
| VC-123 (table part): mostly `�` → unreadable, no DataFrame | same | PASS (`�` simulated, S01-D-010); fewer than a quarter → readable |
| VC-161: script twice → same Tables (and same bytes); ACME multi-page + merged header + R&D + gross/net + regional without national row; values equal constants | `.venv/bin/python -m pytest -q tests/unit/test_sample_pdfs.py` | PASS: 12 cases, including committed PDFs = fresh run, Informe European decimals, shared regions, the chart image reported on page 3 |
| VC-126: heading, caption above/below, paragraphs, footnote; 2-line fallback or empty | `.venv/bin/python -m pytest -q tests/unit/test_context.py` | PASS (+ Tabla/Cuadro, table in between, footnote markers) |
| VC-127: other column, running header, page number → in no field | same | PASS |
| VC-128: pages 2–3, caption on 2, footnote on 3 → both; section from page 1 | same | PASS |
| VC-129: 5,000 characters → ≤ 2,000; section and caption intact | same | PASS |
| VC-169 (context part): 1-page keeps caption and paragraph; 4-page header line not counted | same | PASS |
| ACME (and Informe) Tables each get a non-empty caption | same | PASS |
| Full suite green | `.venv/bin/python -m pytest -q` | PASS: 334 passed, 1 deselected in 33.7 s (baseline 284) |

## TDD evidence
- `test_tables.py` first: collection `ModuleNotFoundError: agents.ingestion.pdf.tables`. First code:
  19/21. Fixes: the test assumed PyMuPDF finds 1-column tables; boxes `(x0, y0, x1, y1)` were passed
  where `flatten_headers` expects `(x0, x1)`.
- `test_sample_pdfs.py` first: `ImportError` (no script). Then 12/12.
- `test_context.py` first: `ModuleNotFoundError`. First code: 7 failures. FR-124's literal overlap
  rule dropped full-width paragraphs (the student chose S01-D-011), plus ligatures (`ﬁ`) and MuPDF
  merging lines of two columns into one block (S01-D-012). Then 17/17.

## Files
Added: `agents/ingestion/schemas.py`, `agents/ingestion/pdf/tables.py`, `agents/ingestion/pdf/context.py`,
`scripts/make_sample_pdfs.py`, `data/sample_pdfs/acme-annual-report-2023.pdf`,
`data/sample_pdfs/informe-regional-2024.pdf`, `tests/unit/test_tables.py`, `tests/unit/test_sample_pdfs.py`,
`tests/unit/test_context.py`, this record.
Changed: `tests/pdf_fixtures.py` (`Page.right`, `top_line`, `bottom_line`), `.gitignore` (+ `data/tables/`),
`specs/01-ingestion-plan-artifacts/CONTEXT.md`, `…/DECISIONS.md` (S01-D-008 … S01-D-013).
Deleted: none. `pdf/cleaning.py` is unchanged (an experimental tolerance edit was reverted).

## Decisions
S01-D-008 (header clues in code), S01-D-009 (`extract_tables(doc, sha)`, positions, joins),
S01-D-010 (fixture limits), S01-D-011 (FR-124 overlap = half the narrower),
S01-D-012 (context details), S01-D-013 (sample contents). All accepted by the student (2026-10-12).

## Deviations
- `extract_tables` takes the document hash as a second argument (plan: `extract_tables(doc)`), S01-D-009.
- FR-124 implemented as S01-D-011, not as the spec's literal wording. The spec tab must reword it.
- `scripts/make_sample_pdfs.py` is 371 lines: mostly table data and page text. D-034's ~300-line
  guide targets library modules.
- Spec 02 interfaces (`read_table`, `load_catalog`, Index record fields, `preview`) are untouched.

## Gotchas
- `find_tables()` treats row 0 as the header of every table, even a plain data row.
- Bold = span flag 16 (`pymupdf.TEXT_FONT_BOLD`). Story's `<th>` and `<b>` are bold; `insert_text`
  with `fontname="hebo"` is bold too.
- `Table.rows[i].cells` holds full boxes; a merged cell's box spans its columns and the covered
  positions are `None`. A column's end is the smallest right edge among its real cells (the table
  bbox can differ from the cell edge by float noise).
- `get_text("dict")` keeps ligatures by default; table cell text does not.
- `doc.tobytes()` changes on every save unless `no_new_id=True` is passed.

## For the next iteration
- Iteration 4 (prompt + Table store): the human message's `Columns` table takes names from
  `ExtractedTable.columns`, dtypes from `frame.dtypes` (`object` → `text`) and hints from
  `ExtractedTable.hints`; `First rows` from `frame.head(20)`. The context fields come from
  `TableContext`; an empty field is printed as `not found`.
- Iteration 5 (graph): `load_pdf` computes `document_sha(data)` and passes it to `extract_tables`.
  Unreadable `ExtractedTable`s become "a table on page N" bullets and never reach `collect_context`.
  The live test can assert the ACME shape: 5 Tables, pages [[1], [1], [2], [3], [4, 5]].
- Student review/staging/commit is next. Suggested message: `Spec 01 · Iter 3: Extract tables from
  PDFs, add the sample PDFs and collect each table's context`.
