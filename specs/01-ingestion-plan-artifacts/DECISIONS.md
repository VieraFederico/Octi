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
**Consequences**: Covered by `test_bytes_that_are_not_a_pdf_are_unreadable[png]`. Student to confirm.

## S01-D-003: The same image on several pages is recognised by its content hash  (Iteration 1)
**Context**: FR-121's repetition rule needs "the same image"; the spec does not say how to tell.
**Decision**: `page.get_image_info(hashes=True)["digest"]` (MD5 of the image's pixels). An image
counts on a page whatever its size there; it is repeated when `is_repeated(pages, page_count)`.
**Rejected**: `xref` (PDF object number) — some writers store one copy of a logo per page, and inline
images have xref 0; position/size — two different charts in the same spot would merge.
**Consequences**: identical pixels at different sizes count as one image. Student to confirm.

## S01-D-004: Document leaves carry their fixed sentence and take no argument  (Iteration 1)
**Context**: Spec 00 leaves receive their `user_message` from the raising code. The three document
sentences are fixed by FR-105 … FR-107 and must be identical wherever they are raised.
**Decision**: `DocumentError.message` (class attribute, like `ExternalServiceError.service`) and a
no-argument `__init__`: `raise DocumentEncryptedError()`. `TableStoreError` keeps the spec 00 shape
(the caller passes the message), because a read failure and a write failure say different things.
**Rejected**: module constants in `pdf/document.py` passed at each raise — the sentence would live far
from the error and could drift between callers.
**Consequences**: `tests/unit/test_errors.py` builds document leaves with no argument.

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
