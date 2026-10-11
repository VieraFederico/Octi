"""Open the uploaded PDF and find what Octi cannot read in it (spec 01 FR-105 … FR-107, FR-119, FR-121).

Deterministic, no LLM. The functions work on the open PyMuPDF document itself — there is no wrapper
class (D-084). The caller owns the document and closes it: `with open_document(data) as doc: ...`.

- Whole-file problems stop the run before any LLM call: `open_document` raises a `DocumentError`
  leaf whose `user_message` is the spec's sentence.
- Pages without selectable text are Skipped parts (FR-119): `pages_without_text`.
- Large images on readable pages may hide a table, so the run summary names their pages (FR-121):
  `reported_image_pages`.
Page numbers in every result are 1-based, as the user sees them.
"""

from collections import defaultdict

import pymupdf

from services.errors import (
    DocumentEncryptedError,
    DocumentError,
    DocumentUnreadableError,
    DocumentWithoutTextError,
)

# Code constants (spec 01 §7), not configuration.
MIN_IMAGE_PAGE_FRACTION = 0.02  # a reported image covers at least 2 % of the page area
MIN_PAGES_FOR_REPETITION = 3  # "repeated on more than half of the pages" applies from 3 pages (D-080)


def open_document(data: bytes) -> pymupdf.Document:
    """Open PDF bytes in memory, or raise the `DocumentError` leaf that says why the file is refused.

    Unreadable (FR-105) → password-protected (FR-106) → no selectable text on any page (FR-107).
    On a refusal the document is closed before raising; otherwise the caller closes it.
    """
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except pymupdf.FileDataError as exc:  # PyMuPDF wraps every open failure (also empty bytes) in it
        raise DocumentUnreadableError() from exc
    problem = _whole_file_problem(doc)
    if problem is not None:
        doc.close()
        raise problem
    return doc


def _whole_file_problem(doc: pymupdf.Document) -> DocumentError | None:
    """The reason the whole file cannot be ingested, or `None` when it can."""
    # MuPDF recognises a file by its content, so an image renamed to .pdf opens as a one-page
    # document; it is still "not a real PDF" (S01-D-002).
    if not doc.is_pdf:
        return DocumentUnreadableError()
    # `needs_pass` = a password is required to read anything. A PDF with only an owner password
    # (permission flags) opens without one and is readable, so `is_encrypted` is not used.
    if doc.needs_pass:
        return DocumentEncryptedError()
    if len(pages_without_text(doc)) == doc.page_count:
        return DocumentWithoutTextError()
    return None


def pages_without_text(doc: pymupdf.Document) -> list[int]:
    """The 1-based numbers of the pages with no selectable text, e.g. scanned pages (FR-119)."""
    return [page.number + 1 for page in doc if not page.get_text().strip()]


def is_repeated(pages_with_it: int, page_count: int) -> bool:
    """Whether something found on `pages_with_it` pages counts as repeated (running text, logos).

    Repeated = on more than half of the pages, and only in PDFs of at least 3 pages: in a 1- or
    2-page PDF everything would otherwise count as repeated (D-080).
    """
    return page_count >= MIN_PAGES_FOR_REPETITION and pages_with_it > page_count / 2


def reported_image_pages(doc: pymupdf.Document) -> list[int]:
    """The 1-based numbers of the pages whose images the run summary must mention (FR-121).

    A page is reported when it has selectable text and holds at least one image that covers at least
    2 % of the page area and is not repeated (`is_repeated`). Pages without text are not reported
    here: they are already Skipped parts (FR-119).

    The same image on several pages is recognised by its content hash (`digest`, MD5 of the pixels),
    not by its PDF object number (`xref`): some PDF writers store one copy of a logo per page, and
    inline images have no object number at all (S01-D-003).
    """
    pages_by_image: dict[bytes, set[int]] = defaultdict(set)  # image digest → pages showing it
    large_images_by_page: dict[int, set[bytes]] = defaultdict(set)  # page → digests of large images
    for page in doc:
        number = page.number + 1
        for image in page.get_image_info(hashes=True):
            pages_by_image[image["digest"]].add(number)
            if _page_fraction(pymupdf.Rect(image["bbox"]), page.rect) >= MIN_IMAGE_PAGE_FRACTION:
                large_images_by_page[number].add(image["digest"])

    without_text = set(pages_without_text(doc))
    return [
        number
        for number, digests in sorted(large_images_by_page.items())
        if number not in without_text
        and any(not is_repeated(len(pages_by_image[digest]), doc.page_count) for digest in digests)
    ]


def _page_fraction(box: pymupdf.Rect, page_rect: pymupdf.Rect) -> float:
    """The share of the page area covered by `box`, counting only its part inside the page."""
    return (box & page_rect).get_area() / page_rect.get_area()
