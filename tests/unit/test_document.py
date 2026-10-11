"""Reading the uploaded PDF: whole-file problems, pages without text, reported images (spec 01
FR-105 … FR-107, FR-119 page part, FR-121). Function level; the graph-level checks come later."""

import pymupdf
import pytest

from agents.ingestion.pdf.document import open_document, pages_without_text, reported_image_pages
from services.errors import DocumentEncryptedError, DocumentUnreadableError, DocumentWithoutTextError
from tests.pdf_fixtures import Image, encrypt, image_covering, image_only_page, make_pdf, text_page

LARGE = 0.10  # of the page area: well above the 2 % rule
LOGO = image_covering(0.005, shade=30)  # a small logo: 0.5 % of the page


def png_bytes() -> bytes:
    """A real PNG image: PyMuPDF opens it as a one-page document, but it is not a PDF."""
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 8, 8), False)
    pixmap.clear_with(90)
    return pixmap.tobytes("png")


# --- open_document -----------------------------------------------------------------------------


@pytest.mark.parametrize("data", [b"not a pdf", b"", png_bytes()], ids=["text", "empty", "png"])
def test_bytes_that_are_not_a_pdf_are_unreadable(data: bytes) -> None:
    """VC-105 (FR-105): bytes PyMuPDF cannot open as a PDF → the FR-105 sentence."""
    # Given bytes that are not a PDF / When they are opened / Then the unreadable leaf is raised
    with pytest.raises(DocumentUnreadableError) as caught:
        open_document(data)
    assert caught.value.user_message == "I couldn't open this file. It may be damaged or not a real PDF."


def test_password_protected_pdf_is_refused() -> None:
    """VC-106 (FR-106): a PDF that needs a password to open → the FR-106 sentence."""
    # Given a readable PDF encrypted with a user password
    data = encrypt(make_pdf(text_page("Annual report")), user_password="secret")
    # When it is opened / Then the encrypted leaf is raised
    with pytest.raises(DocumentEncryptedError) as caught:
        open_document(data)
    assert caught.value.user_message == "This PDF is password-protected. Remove the password and upload it again."


def test_pdf_with_only_an_owner_password_opens() -> None:
    """FR-106 boundary: permission flags without a user password do not block reading."""
    # Given a PDF encrypted with an owner password only
    data = encrypt(make_pdf(text_page("Annual report")), user_password="")
    # When it is opened / Then it is an ordinary readable document
    with open_document(data) as doc:
        assert doc.page_count == 1
        assert "Annual report" in doc[0].get_text()


def test_pdf_without_selectable_text_is_refused() -> None:
    """VC-107 (FR-107): every page holds only an image → the FR-107 sentence."""
    # Given a PDF whose two pages are images only
    data = make_pdf(image_only_page(), image_only_page())
    # When it is opened / Then the no-text leaf is raised
    with pytest.raises(DocumentWithoutTextError) as caught:
        open_document(data)
    assert caught.value.user_message == (
        "This PDF has no selectable text (it looks scanned). I can only read PDFs with selectable text."
    )


def test_readable_pdf_is_returned_open() -> None:
    """FR-105 … FR-107 happy path: the open PyMuPDF document itself comes back (no wrapper, D-084)."""
    # Given a two-page PDF with text / When it is opened
    with open_document(make_pdf(text_page("Page one"), text_page("Page two"))) as doc:
        # Then it is a PyMuPDF document, ready to read
        assert isinstance(doc, pymupdf.Document)
        assert doc.page_count == 2


# --- pages_without_text ------------------------------------------------------------------------


def test_pages_without_text_are_listed_1_based() -> None:
    """VC-123 (FR-119 page part): pages 2–3 image-only in a 4-page PDF → [2, 3]."""
    # Given a 4-page PDF whose pages 2 and 3 are images only
    data = make_pdf(text_page("One"), image_only_page(), image_only_page(), text_page("Four"))
    # When it is opened (some pages have text, so it is not refused) and checked
    with open_document(data) as doc:
        # Then pages 2 and 3 are reported, numbered from 1
        assert pages_without_text(doc) == [2, 3]


def test_pdf_with_text_everywhere_has_no_page_without_text() -> None:
    """FR-119: nothing to report when every page has selectable text."""
    with open_document(make_pdf(text_page("One"), text_page("Two"))) as doc:
        assert pages_without_text(doc) == []


# --- reported_image_pages ----------------------------------------------------------------------


def test_large_image_is_reported_and_a_repeated_small_logo_is_not() -> None:
    """VC-125 (FR-121): a large image on page 5 and a small logo on every page → only page 5."""
    # Given 6 text pages with the same small logo, and a large image on page 5
    pages = [text_page(f"Page {number}", LOGO) for number in range(1, 7)]
    pages[4] = text_page("Page 5", LOGO, image_covering(LARGE))
    # When the image pages are computed / Then only page 5 is reported
    with open_document(make_pdf(*pages)) as doc:
        assert reported_image_pages(doc) == [5]


def test_one_page_pdf_reports_its_large_image() -> None:
    """VC-169 (FR-121 image part, D-080): in a 1-page PDF the repetition rule does not apply."""
    with open_document(make_pdf(text_page("Table 1. Sales", image_covering(LARGE)))) as doc:
        assert reported_image_pages(doc) == [1]


def test_large_image_repeated_on_every_page_is_not_reported() -> None:
    """VC-169 (FR-121, D-080): a 4-page PDF with the same large image on every page → none reported."""
    # Given a background image (identical pixels) on all 4 pages
    background = image_covering(LARGE, shade=60)
    pages = [text_page(f"Page {number}", background) for number in range(1, 5)]
    # When the image pages are computed / Then the repeated image is ignored
    with open_document(make_pdf(*pages)) as doc:
        assert reported_image_pages(doc) == []


def test_image_on_exactly_half_the_pages_is_still_reported() -> None:
    """FR-121: "repeated" means on MORE than half of the pages; 2 of 4 is not repeated."""
    chart = image_covering(LARGE, shade=70)
    pages = [text_page("One", chart), text_page("Two"), text_page("Three", chart), text_page("Four")]
    with open_document(make_pdf(*pages)) as doc:
        assert reported_image_pages(doc) == [1, 3]


def test_repetition_rule_needs_at_least_3_pages() -> None:
    """D-080: in a 2-page PDF the same large image on both pages is reported on both."""
    chart = image_covering(LARGE, shade=70)
    with open_document(make_pdf(text_page("One", chart), text_page("Two", chart))) as doc:
        assert reported_image_pages(doc) == [1, 2]


def test_image_area_threshold_is_2_percent_of_the_page() -> None:
    """FR-121 (SPEC §7 code constants): 1.9 % of the page is ignored, 2.1 % is reported."""
    pages = [text_page("Small", image_covering(0.019, shade=40)), text_page("Big", image_covering(0.021, shade=50))]
    with open_document(make_pdf(*pages)) as doc:
        assert reported_image_pages(doc) == [2]


def test_image_area_counts_only_the_part_on_the_page() -> None:
    """FR-121: an image mostly outside the page counts only by its visible part."""
    # Given a 300 x 300 pt image of which only a 10 x 300 strip is on the page (0.6 % of it)
    width = 595  # A4 width in points
    off_page = Image((width - 10, 100, width + 290, 400), shade=80)
    with open_document(make_pdf(text_page("Edge", off_page))) as doc:
        assert reported_image_pages(doc) == []


def test_image_on_a_page_without_text_is_not_an_image_note() -> None:
    """FR-121 applies to pages with selectable text; an image-only page is reported by FR-119 instead."""
    data = make_pdf(text_page("One"), image_only_page(), text_page("Three"))
    with open_document(data) as doc:
        assert pages_without_text(doc) == [2]
        assert reported_image_pages(doc) == []
