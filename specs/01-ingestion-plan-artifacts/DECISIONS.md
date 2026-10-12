# Spec 01 — decisions taken during implementation (S01-D-NNN)

Spec-local choices the spec, the plan and the root `DECISIONS.md` leave open (root D-004). Each entry
names the iteration that made it. Project-wide decisions go to the root log as `D-NNN` instead.

## S01-D-001: Fixture tables come from HTML through PyMuPDF's Story (A-102 holds)  (Iteration 1)
**Context**: A-102 / D-070 asked whether PyMuPDF's HTML → PDF draws merged cells (`colspan`) that
`find_tables()` reports; otherwise the fixtures would draw tables with the drawing API.
**Decision**: Story works, so `tests/pdf_fixtures.py` writes tables as HTML (`<th colspan="2">`) and
draws each page with `Page.insert_htmlbox` (Story inside), one fixture `Page` = one PDF page; blocks
that do not fit raise instead of spilling over. Observed with PyMuPDF 1.28.2: the merged cell's box
spans both columns, the covered position is `None` (text and box), an empty cell is `""` with a box.
**Rejected**: drawing API (lines + `insert_text`) — more code per fixture, not needed;
`DocumentWriter` + `Story.place` — content flows across pages, so page numbers drift and images
cannot be added to a chosen page in the same step.
**Consequences**: Iteration 3's `scripts/make_sample_pdfs.py` can use the same HTML approach.

## S01-D-002: A file MuPDF opens but that is not a PDF is "unreadable"  (Iteration 1)
**Context**: MuPDF recognises files by content, so a PNG renamed to `.pdf` opens as a 1-page
document even with `filetype="pdf"`; it would then fail as "no selectable text (looks scanned)".
**Decision**: `open_document` checks `doc.is_pdf` and raises `DocumentUnreadableError` (FR-105:
"… may be damaged or not a real PDF.") for anything that is not a PDF.
**Rejected**: let it fall through to FR-107 — the sentence would blame a scan for a non-PDF.
**Consequences**: Covered by `test_bytes_that_are_not_a_pdf_are_unreadable[png]`.
**Status**: accepted by the student (2026-10-11).

## S01-D-003: The same image on several pages is recognised by its content hash  (Iteration 1)
**Context**: FR-121's repetition rule needs "the same image"; the spec does not say how to tell.
**Decision**: `page.get_image_info(hashes=True)["digest"]` (MD5 of the image's pixels). An image
counts on a page whatever its size there; it is repeated when `is_repeated(pages, page_count)`.
**Rejected**: `xref` (PDF object number) — some writers store one copy of a logo per page, and inline
images have xref 0; position/size — two different charts in the same spot would merge.
**Consequences**: identical pixels at different sizes count as one image.
**Status**: accepted by the student (2026-10-11).

## S01-D-004: Document leaves carry their fixed sentence and take no argument  (Iteration 1)
**Context**: Spec 00 leaves receive their `user_message` from the raising code. The three document
sentences are fixed by FR-105 … FR-107 and must be identical wherever they are raised.
**Decision**: `DocumentError.message` (class attribute, like `ExternalServiceError.service`) and a
no-argument `__init__`: `raise DocumentEncryptedError()`. `TableStoreError` keeps the spec 00 shape
(the caller passes the message), because a read failure and a write failure say different things.
**Rejected**: module constants in `pdf/document.py` passed at each raise — the sentence would live far
from the error and could drift between callers.
**Consequences**: `tests/unit/test_errors.py` builds document leaves with no argument.
**Status**: accepted by the student (2026-10-11).

## S01-D-005: What "no selectable text" and "an image on a page with text" mean in code  (Iteration 1)
**Context**: FR-107, FR-119 and FR-121 name the conditions but not their test in code.
**Decision**: a page has no selectable text when `page.get_text().strip()` is empty (an invisible OCR
text layer is selectable text, so it counts as text). FR-121 reports only pages that have text;
an image-only page is already a Skipped part under FR-119 and is not reported twice. The 2 % rule
uses the image's box clipped to the page (`(bbox & page.rect)` area / page area).
**Rejected**: counting characters or words per page (a threshold the spec does not have); reporting
image-only pages in both lists.
**Consequences**: Iteration 7 builds the FR-119 bullets from `pages_without_text` and the FR-121
note from `reported_image_pages`, without overlap.

## S01-D-006: Cleaning helpers use plain tuples, lists and coordinate spans (Iteration 2)
**Context**: The plan leaves helper names and input/result shapes to implementation.
**Decision**: `flatten_headers(header_rows, spans, column_spans)` returns names; spans are horizontal
`(x0, x1)` pairs or `None`. `clean_column(values)` returns `(Series, list[str])`;
`build_dataframe(names, rows)` returns `(DataFrame, dict[str, list[str]])`. Hints are distinct,
first-seen `percent` / `currency: <symbol>` strings, empty on failed numeric conversion.
`row_headers(frame)` returns only non-missing labels from the first column, retaining that column.
**Rejected**: custom result classes, a single hint string, logical colspan inputs, missing labels
as row headers — more indirection or less faithful geometry/data than the existing extraction shape.
**Consequences**: Iteration 3 supplies rectangular/aligned grids, real spans and column extents;
Iteration 5 consumes hints directly. No spec 02 interface or metadata schema changes.
**Status**: accepted by the student (2026-10-11).

## S01-D-007: Whole columns outside signed int64 range remain text (Iteration 2)
**Context**: FR-117 requires int64 for whole columns without gaps, but specifies no overflow policy;
PyMuPDF can supply digit strings beyond int64's representable range.
**Decision**: Only columns that would require int64 are range-checked. A value outside
`[-2**63, 2**63 - 1]` keeps the whole column as original text with no hints. The bounds are inclusive;
fractional or missing numeric columns still use float64 as FR-117 requires.
**Rejected**: rounding to float64, adding another metadata dtype, or raising an overflow error.
**Consequences**: Such whole columns cannot crash int64 construction or silently round their values;
the existing int64/float64/text contract for spec 02 is unchanged.
**Status**: accepted by the student (2026-10-11).

## S01-D-008: How the header-row clues of FR-113 step 1 are read in code (Iteration 3)
**Context**: FR-113 names the clues but not how to test them on PyMuPDF output, which marks the
first row of every table as its "header", even a plain data row (VC-113 says such a row is data).
**Decision**: Every top row, PyMuPDF's header row included, needs a clue. A row is bold when every
text span centred in it has the bold font flag (16). The bold clue holds when some row below is not
bold. A merge is a real cell wider than its column by more than 0.5 pt. A data value is a cell
`clean_column` turns numeric; a year is four plain digits from 1900 to 2100 (not `2,000`). A
one-row table whose row shows a clue has "no data row" (FR-110). A cap of 3 header rows applies, and
at least 1 data row always remains.
**Rejected**: trusting PyMuPDF's header row (VC-113 fails); "first data row" = the row right after
the candidates (circular); any whole number 1900–2100 (a value of `2,000` would make a row a label).
**Consequences**: PyMuPDF's "external" headers (text above a borderless table) are ignored; that
falls under the borderless-tables limitation.
**Status**: accepted by the student (2026-10-12).

## S01-D-009: `extract_tables(doc, sha)` and how positions and joins are counted (Iteration 3)
**Context**: The plan names `extract_tables(doc)`, but `table_id` needs the hash of the original PDF
bytes, which an open document does not expose cleanly.
**Decision**: `extract_tables(doc, sha)` takes the hash from `document_sha(data)`, which the graph also
needs for the Index record. Positions count every table PyMuPDF finds on the page, so a dropped fake
table keeps its slot and ids do not shift when the filter changes. Only kept, readable tables join.
An unreadable table is never joined and ends any open chain.
**Rejected**: reading `doc.stream` (hidden dependency on how the document was opened); positions
among kept tables only.
**Consequences**: Iteration 5's `extract_tables` node passes the hash it computed in `load_pdf`.
**Status**: accepted by the student (2026-10-12).

## S01-D-010: What fixture PDFs cannot show, and how the tests cover it (Iteration 3)
**Context**: PyMuPDF 1.28.2's HTML engine draws U+FFFD as another glyph (it extracts as `蓣`), and
rewriting a font's ToUnicode makes MuPDF fall back to glyph ids, never to `�`. `find_tables()`
reports no 1-column table at all.
**Decision**: VC-123's table part patches `pymupdf.table.Table.extract` in that test only, so cells
marked `GARBLED` read as `�`. The FR-110 `< 2 columns` check stays as a guard, and VC-109 asserts
that the 1-column box never becomes a Table.
**Rejected**: committing a real damaged PDF (binary fixture, against D-070); dropping the guard.
**Consequences**: the rule itself (`_is_unreadable`) runs on real extraction output; only the source of
the `�` text is simulated.
**Status**: accepted by the student (2026-10-12).

## S01-D-011: FR-124's overlap rule uses the narrower of the block and the Table (Iteration 3)
**Context**: FR-124 as written ("overlaps the Table horizontally by at least half of the block's
width") drops every full-width paragraph and heading above a table narrower than half the text width,
so VC-126 itself fails and real reports lose most of their context.
**Decision**: A block counts when its horizontal overlap with the Table is at least half the width of
the narrower of the two. Text in the other column of a two-column page still overlaps 0 and never
counts.
**Rejected**: half the Table's width (a short heading over a wide table would be lost); keeping the
literal rule and narrowing the fixtures.
**Consequences**: the spec tab rewords FR-124 (spec 01 text change; no interface change).
**Status**: accepted by the student (2026-10-12).

## S01-D-012: Context details the spec leaves open (Iteration 3)
**Context**: FR-123 names the fields; some roles overlap in practice.
**Decision**: A heading is never the caption fallback, `before` or `after` (it is the section). Footnote
lines are joined with line breaks. Each MuPDF block is split into groups of lines that overlap
horizontally, because MuPDF merges lines of two columns at the same height into one block. Ligatures
are expanded (`ﬁ` → `fi`). Cuts are plain slices (no ellipsis).
**Rejected**: using whole MuPDF blocks (VC-127 fails); keeping ligatures (names unsearchable).
**Consequences**: `collect_context(doc, table)` reads the page layout once per call; Iteration 5 may
call it once per Table without caching (sample PDFs: well under a second).
**Status**: accepted by the student (2026-10-12).

## S01-D-013: Sample PDF contents and constants (Iteration 3)
**Context**: D-070 lists the hard cases and D-107 adds the test-question tables. The data and its
names were left to the script.
**Decision**: ACME (5 pages, years 2021–2023, USD millions): income with gross/net revenue, net income
`$(12.4)` and net margin %, R&D expenses and staff, regional net sales and market share (two-row
merged header, regions Patagonia, Cuyo, Pampa, NOA, NEA, no national row), headcount with `n/a` on a
two-column page with one chart image, and monthly net sales (USD thousands) over pages 4–5 with the
header repeated. The constants agree with each other: regions sum to net revenue, and the months sum
to it ×1000. The Informe (Spanish, 1 page) holds population (thousands) and labour rates for the same
five regions. Deterministic save: `tobytes(garbage=3, deflate=True, no_new_id=True)`, empty metadata.
**Rejected**: hand-typed tables in HTML; national totals in either PDF (they would answer question 9).
**Consequences**: spec 03 imports the constants listed in `CONTEXT.md`. The PDFs are byte-identical
for the same PyMuPDF version.
**Status**: accepted by the student (2026-10-12).
