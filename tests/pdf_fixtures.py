"""Builders for tiny fixture PDFs, returned as bytes. A plain module: tests import from it.

A test describes each page with a `Page` (HTML blocks plus images) and `make_pdf` draws them with
PyMuPDF, in memory. HTML goes through `pymupdf.Page.insert_htmlbox`, which uses PyMuPDF's Story
engine (HTML → PDF): tables get ruling lines, and `colspan` draws a real merged cell that
`find_tables()` reports (spec A-102, S01-D-001). Building report pages from HTML follows the course
playground's PDF-tables lesson generator.

Each test builds exactly the case it checks, so no binary fixture file has to be kept in the repo.
"""

import html
from collections.abc import Sequence
from dataclasses import dataclass

import pymupdf

PAGE_RECT = pymupdf.paper_rect("a4")  # 595 x 842 points
MARGIN = 36  # half an inch on every side
CONTENT_RECT = PAGE_RECT + (MARGIN, MARGIN, -MARGIN, -MARGIN)

# Ruled cells, so `find_tables()` sees the table by its lines.
CSS = """
body { font-family: sans-serif; font-size: 10pt; }
table { border-collapse: collapse; }
th, td { border: 1px solid black; padding: 2pt 6pt; }
"""


# --- HTML blocks -------------------------------------------------------------------------------


def heading(text: str) -> str:
    """A section heading block."""
    return f"<h2>{html.escape(text)}</h2>"


def paragraph(text: str) -> str:
    """A paragraph block."""
    return f"<p>{html.escape(text)}</p>"


def _row(cells: Sequence[str], tag: str) -> str:
    return "<tr>" + "".join(f"<{tag}>{html.escape(cell)}</{tag}>" for cell in cells) + "</tr>"


def table(
    header: Sequence[str],
    rows: Sequence[Sequence[str]] = (),
    *,
    merged_header: Sequence[tuple[str, int]] = (),
) -> str:
    """A ruled table block.

    `header` is the header row (`()` = no header row); `rows` are the data rows. `merged_header` is an
    optional row above `header` made of `(text, columns spanned)` cells, e.g.
    `(("Region", 1), ("Revenue", 2))` for a "Revenue" cell over two columns.
    """
    top = ""
    if merged_header:
        cells = (f'<th colspan="{span}">{html.escape(text)}</th>' for text, span in merged_header)
        top = "<tr>" + "".join(cells) + "</tr>"
    head = _row(header, "th") if header else ""
    body = "".join(_row(row, "td") for row in rows)
    return f"<table>{top}{head}{body}</table>"


# --- Images ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Image:
    """An image drawn on a page: its rectangle in points and its gray level.

    Two images with the same `shade` have identical pixels, so PyMuPDF sees them as the same image
    (a logo repeated on every page); different shades are different images.
    """

    rect: tuple[float, float, float, float]
    shade: int = 128


def image_covering(fraction: float, *, shade: int = 128) -> Image:
    """A square image covering `fraction` of the page area, in the bottom-left corner of the content."""
    side = (fraction * PAGE_RECT.get_area()) ** 0.5
    if side > CONTENT_RECT.width:
        raise ValueError(f"an image covering {fraction:.0%} of the page does not fit inside the margins")
    bottom = PAGE_RECT.height - MARGIN
    return Image((MARGIN, bottom - side, MARGIN + side, bottom), shade)


def _pixmap(shade: int) -> pymupdf.Pixmap:
    """An 8 x 8 RGB image filled with one gray level; PyMuPDF scales it to the target rectangle."""
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 8, 8), False)
    pixmap.clear_with(shade)
    return pixmap


# --- Pages and documents -----------------------------------------------------------------------


@dataclass(frozen=True)
class Page:
    """One fixture page: HTML blocks drawn top to bottom, then images drawn on top of them."""

    blocks: tuple[str, ...] = ()
    images: tuple[Image, ...] = ()


def image_only_page(shade: int = 200) -> Page:
    """A page with one large image and no selectable text, like a scanned page."""
    return Page(images=(image_covering(0.5, shade=shade),))


def text_page(text: str, *images: Image) -> Page:
    """A page with one paragraph of text and the given images."""
    return Page(blocks=(paragraph(text),), images=images)


def make_pdf(*pages: Page) -> bytes:
    """Draw the pages, in order, into a new PDF and return its bytes.

    Each page's blocks must fit on that page: a fixture never spills onto an extra page, so page
    numbers in tests are exactly the positions of the `Page`s (1-based).
    """
    with pymupdf.open() as doc:
        for number, spec in enumerate(pages, start=1):
            page = doc.new_page(width=PAGE_RECT.width, height=PAGE_RECT.height)
            if spec.blocks:
                # scale_low=1: never shrink the text to make it fit; report the overflow instead.
                spare_height, _scale = page.insert_htmlbox(CONTENT_RECT, "".join(spec.blocks), css=CSS, scale_low=1)
                if spare_height < 0:
                    raise ValueError(f"the blocks of page {number} do not fit on one page")
            for image in spec.images:
                page.insert_image(pymupdf.Rect(image.rect), pixmap=_pixmap(image.shade))
        return doc.tobytes()


def encrypt(pdf: bytes, *, user_password: str = "secret") -> bytes:
    """The same PDF, encrypted with AES-256.

    With a `user_password`, nobody can open it without that password. With `user_password=""` only
    an owner password is set: it opens freely and just carries permission flags.
    """
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        return doc.tobytes(
            encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw=user_password, owner_pw="owner-password"
        )
