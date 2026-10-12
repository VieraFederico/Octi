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

## S01-D-014: `CatalogEntry` also carries `row_headers_total` and a datetime (Iteration 4)
**Context**: D-080 defines `CatalogEntry` = `TableMetadata` + `document_sha`, `ingested_at`, `preview`,
`n_rows`, `n_cols`. A card says "first 10 and N more", but the Index stores only 50 row headers.
**Decision**: add `row_headers_total: int` (the Index already stores it). `row_headers` of an entry
holds at most the first 50. `ingested_at` is a timezone-aware `datetime` (parsed from the ISO text).
**Rejected**: derive "N more" from `n_rows` (row headers skip missing labels and the first column may
be numeric, so the two counts differ).
**Consequences**: spec 02 and the Library read `entry.row_headers_total`. Spec tab: add the field to
SPEC §7 "Catalog interface". Nothing removed.
**Status**: accepted by the student (2026-10-12).

## S01-D-015: `validate` takes a `TableEnrichment` or the raw dict (Iteration 4)
**Context**: the plan leaves open how an answer that does not parse reaches `validate`.
**Decision**: `validate(answer: TableEnrichment | dict, table)`. A dict is checked with
`TableEnrichment.model_validate`; each pydantic error becomes one sentence naming the field
(`columns[2].unit is too long: at most 40 characters`). When the shape fails, only the shape
sentences are returned (nothing else can be read); the next attempt is checked in full. No JSON
string parsing. Iteration 5's `enrich` must hand `validate` the raw dict when structured output
does not parse (`include_raw=True`).
**Rejected**: also accepting a JSON string (a structured-output call does not yield bare text; one more
branch to test).
**Consequences**: a retry's `Previous answer` section accepts the same two types.
**Status**: accepted by the student (2026-10-12).

## S01-D-016: Small signature additions the plan's drafts lacked (Iteration 4)
**Context**: the plan names `build_messages(table, context, previous, feedback)`,
`assemble_metadata(enrichment, table)` and `index_metadata(metadata, table, document)`, but the file
name is not in an `ExtractedTable`, and "document" is only the hash.
**Decision**: `build_messages(table, context, source_file, previous=None, feedback=())`;
`assemble_metadata(enrichment, table, source_file)`; `index_metadata(metadata, table, document_sha,
ingested_at=None)` (the time is a parameter so tests can fix it). Two helpers live in
`pdf/cleaning.py` because both the prompt and the Index record need them: `dtype_name(series)`
(`int64`, `float64`, else `text`) and `rows_as_text(frame, limit, max_cell=None)` (rows as `a | b`
lines, a gap as nothing, a line break as a space). The 20 rows sent to the LLM are not cut per cell
(the preview's 40-character cut is only for the Index).
**Rejected**: a new module for two small functions (D-084 file map); cutting LLM cells (not in the spec).
**Consequences**: a pathological Table (huge cells) can exceed the 24,000-character budget; VC-165
holds for ordinary tables (measured: 15,464 characters for 20 columns x 20 rows with 15-character cells
and 2,000 characters of context). Noted as a known gap.
**Status**: accepted by the student (2026-10-11).

## S01-D-017: `find_versions` uses `fetch_by_metadata`, not a query (Iteration 4)
**Context**: A-103 expected "querying with a metadata filter". The installed SDK (pinecone 10.0.0)
has `Index.fetch_by_metadata(filter=..., pagination_token=...)`, a plain lookup with pagination.
**Decision**: `find_versions` loops `fetch_by_metadata({"source_file": name})` until `pagination` is
empty. A query would need a made-up non-zero vector and is capped by `top_k`.
**Rejected**: `query` with a dummy vector.
**Consequences**: A-103 still holds in spirit (a metadata filter on `source_file`); the live check in
Iteration 7 must confirm `fetch_by_metadata` on the student's serverless index. The record functions
take the namespace as an argument (`list_records(index, namespace)`), and `open_index(settings)`
builds the handle from the index host.
**Status**: accepted by the student (2026-10-12).

## S01-D-018: `write_document` reads before it writes, and rolls back only what it created (Iteration 4)
**Context**: D-067 finds old versions in step 4. If a re-ingest of the same bytes fails at the
upsert, "remove what this run wrote" would also delete the identical version already there (BR-105).
**Decision**: `write_document` first asks Pinecone for the records carrying `source_file`
(a read, so the write order is unchanged and a failing lookup stops the run before anything is
written). Rollback deletes only ids that were not already there. Step 4 deletes every found id that
is not one of the new ids (a superset of "another document hash": ids embed the hash prefix, so
the two sets are equal unless extraction changed between runs). In step 4 records are deleted before
files, so a half-failed delete leaves a record with its file, never a record without a file.
**Rejected**: keep the lookup in step 4 and accept the edge case.
**Consequences**: the same-bytes case is covered by a test. Mutation order is still embed, files,
upsert, delete (VC-140).
**Status**: accepted by the student (rollback and lookup-first 2026-10-12; step-4 wording 2026-10-11).

## S01-D-019: `read_table` returns the frame exactly as extraction built it (Iteration 4)
**Context**: pandas 3 reads text columns from Parquet as its `str` dtype with NaN gaps; extraction
builds `object` columns with `None` gaps.
**Decision**: `read_table` casts every non-numeric column back to `object` and restores `None` for gaps,
so `assert_frame_equal(read_table(id), written)` passes strictly.
**Rejected**: accept `str` and compare through `dtype_name` only.
**Consequences**: the Analyst gets the frame ingestion saw. `write_table` writes through a temporary
file and `os.replace`, so a crash never leaves a half-written file. Ids with a path separator are
refused (`TableStoreError`) because an id is a file name.
**Status**: accepted by the student (cast back 2026-10-12; temporary file and id check 2026-10-11).

## S01-D-020: Record details the spec leaves open (Iteration 4)
**Context**: SPEC §7 fixes the Index record fields; some formats were open.
**Decision**: preview = column names line, then up to 5 rows, `a | b` per line, cells cut to 40
characters, whole text cut to 2,000 (accepted pipe format). The 38 KB guard is measured as the
UTF-8 bytes of the metadata as JSON (`38 * 1024`). The embedding text leaves out the `Row headers`
line when a Table has none. `write_document` takes `TableToIndex` items (metadata, full frame, flat
record metadata built and guard-checked at assembly) and returns `WriteResult(table_ids,
previous_removed)`; with no Tables it makes no call at all. Prompt: the Columns table prints names
unescaped; any run of 3 or more backticks in PDF-derived text becomes the same number of
apostrophes; retry sections come after `First rows` and before `Task`.
**Rejected**: CSV preview; character count for the guard.
**Consequences**: Iteration 5 builds `TableToIndex` and calls `write_document`; Iteration 6's card
reads the preview text as is.
**Status**: accepted by the student (preview format 2026-10-12; the rest 2026-10-11).

## S01-D-021: Chat and pause wording the spec leaves open (Iteration 5)
**Context**: FR-120 / FR-135 say "the chat says the ingestion was cancelled" without a sentence;
FR-134 says "its pages, and its caption when known" without a format; plurals for N = 1.
**Decision**: cancel = "Ingestion cancelled. Nothing from report.pdf was indexed."; a skipped Table's
bullet = `pages 4–5: <caption>` (pages only when no caption), pages as `page 3` / `pages 4–5`;
"Index the other 1 table" and "Indexed 1 table from report.pdf" for N = 1. The interrupt value is a
`PauseQuestion` in parts (intro, bullets, question, choices) so the UI can escape captions.
**Rejected**: one pre-joined text (the UI could not escape PDF text in it).
**Consequences**: constants in `nodes.py`; Iteration 6 renders the parts.
**Status**: accepted by the student (2026-10-11).

## S01-D-022: The deps object and the per-run store (Iteration 5)
**Context**: the plan lists deps = chat model, embeddings, Pinecone index, Table store root, settings.
**Decision**: `IngestionDeps(settings, embeddings, index, make_chat_model=make_chat_model, runs=RunStore())`.
The chat model is a factory called with `settings` in `enrich` (FR-127: always `LLM_MODEL`; the stub
records it). No Table store root: `write_document` already uses `TABLE_STORE_DIR`, which tests move
with `table_store_dir`. The per-run store is an object in deps (isolated per test), not a module
global. `assembled` and `skipped` use the `operator.add` reducer; nodes are `node(state, deps)`.
**Rejected**: a root field nothing would read; a module-level store shared by all tests.
**Consequences**: Iteration 6 builds deps once with `make_deps(settings)` and keeps graph + deps together.
**Status**: accepted by the student (2026-10-11).

## S01-D-023: The recursion limit is computed from a table count taken before the run (Iteration 5)
**Context**: FR-143 computes the limit from T, but LangGraph fixes the limit when a call starts, before
`extract_tables` knows T.
**Decision**: `run_ingestion` counts the tables PyMuPDF finds on every page (`table_upper_bound`)
before streaming: an upper bound of T, since dropping and joining only lower it. `resume_ingestion`
uses `len(tables)` from the saved state.
**Rejected**: an internal breakpoint after `extract_tables` (two root traces per run); a fixed large
limit (not "computed from T", D-052).
**Consequences**: `find_tables` runs once more per page (well under a second on the sample PDFs).
**Status**: accepted by the student (2026-10-11).

## S01-D-024: Sidebar Document clicks use a local Streamlit v2 component (Iteration 6)
**Context**: The HTML expanders must keep opening without a rerun (D-072), while Document names
must navigate within the same Streamlit session. Plain HTML cannot invoke a Python callback.
**Decision**: Use the already-installed v2 component API with a static JavaScript shell. Render
escaped Document markup as component data; a Document button emits its file name as a trigger.
The existing details elements and global styles stay in use. Disable Document buttons while streaming.
**Rejected**: native buttons with native expanders (changes the existing expansion presentation);
ordinary links (open a new session and discard the paused run).
**Consequences**: No new dependency. AppTest covers escaped markup and the Python navigation seam;
the student checks browser clicks in the final iteration. User-approved edits also extend
shared ui/chat.py and tests/stubs.py; spec 02 files are not edited.
**Status**: accepted by the student (2026-10-11).
