"""Collecting the Table context of each extracted Table: section, caption, before, after, footnotes
(spec 01 FR-123 … FR-126, VC-169 context part). Fixture PDFs are built in memory per test."""

from dataclasses import astuple
from pathlib import Path

import pymupdf
import pytest

from agents.ingestion.pdf.context import MAX_CONTEXT_CHARS, MAX_PARAGRAPH_CHARS, collect_context
from agents.ingestion.pdf.tables import document_sha, extract_tables
from agents.ingestion.schemas import TableContext
from scripts import make_sample_pdfs as samples
from tests.pdf_fixtures import Page, heading, image_covering, make_pdf, paragraph, table

ROOT = Path(__file__).resolve().parents[2]
SALES = table(["Region", "Sales"], [["North", "10"], ["South", "12"]])
LONG = "This paragraph explains the figures at length and keeps going for several lines. " * 4


def contexts(data: bytes) -> list[TableContext]:
    """The Table context of every Table in fixture PDF bytes, in Table order."""
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        return [collect_context(doc, t) for t in extract_tables(doc, document_sha(data))]


def all_text(context: TableContext) -> str:
    """Every field of a context, joined, for "not anywhere" checks."""
    return "\n".join(astuple(context))


# --- FR-123: the five fields ----------------------------------------------------------------------


def test_each_field_is_found() -> None:
    """VC-126 (FR-123): heading, paragraph above, caption above, table, footnote, paragraph below →
    each in its field."""
    # Given a page with every kind of surrounding text
    data = make_pdf(
        Page(
            blocks=(
                heading("Sales overview"),
                paragraph("Sales grew in every region during the year."),
                paragraph("Table 2. Sales by region"),
                SALES,
                paragraph("(1) Excludes taxes."),
                paragraph("The north led the growth."),
            )
        )
    )
    # When the context is collected
    (context,) = contexts(data)
    # Then each text lands in its own field
    assert context == TableContext(
        section="Sales overview",
        caption="Table 2. Sales by region",
        before="Sales grew in every region during the year.",
        after="The north led the growth.",
        footnotes="(1) Excludes taxes.",
    )


def test_caption_below_the_table_is_found() -> None:
    """VC-126 (FR-123): no caption above, `Table N` just below → `caption`; the paragraph after it
    is `after`."""
    # Given a caption under the table
    data = make_pdf(
        Page(blocks=(heading("Costs"), paragraph(LONG), SALES, paragraph("Table 3. Costs by region"), paragraph("Costs fell.")))
    )
    # When collected / Then the caption below is found and the paragraphs keep their roles
    (context,) = contexts(data)
    assert context.caption == "Table 3. Costs by region"
    assert context.before == LONG.strip()
    assert context.after == "Costs fell."


@pytest.mark.parametrize("word", ["Tabla", "Cuadro"])
def test_spanish_captions(word: str) -> None:
    """FR-123: captions may start with `Tabla N` or `Cuadro N`."""
    # Given a Spanish caption above a table, under a long paragraph
    data = make_pdf(Page(blocks=(paragraph(LONG), paragraph(f"{word} 4. Ventas por región"), SALES)))
    # When collected / Then it is the caption
    (context,) = contexts(data)
    assert context.caption == f"{word} 4. Ventas por región"


def test_short_block_above_is_the_caption_fallback() -> None:
    """VC-126 (FR-123): no `Table N` → a block of at most 2 lines directly above is the caption."""
    # Given a long paragraph, then a one-line block right above the table
    data = make_pdf(Page(blocks=(paragraph(LONG), paragraph("Regional sales in USD millions"), SALES)))
    # When collected / Then the short block is the caption and the long one is `before`
    (context,) = contexts(data)
    assert context.caption == "Regional sales in USD millions"
    assert context.before == LONG.strip()


def test_no_caption_at_all() -> None:
    """VC-126 (FR-123): no `Table N` and the block above is longer than 2 lines → empty caption."""
    # Given only a long paragraph above the table
    data = make_pdf(Page(blocks=(paragraph(LONG), SALES)))
    # When collected / Then no caption, and the paragraph is `before`
    (context,) = contexts(data)
    assert context.caption == ""
    assert context.before == LONG.strip()


def test_another_table_in_between_breaks_just_above() -> None:
    """FR-123 ("just" = no other text block or table in between): a caption above another table
    belongs to that table only."""
    # Given caption, table A, table B
    data = make_pdf(
        Page(blocks=(paragraph("Table 1. Sales by region"), SALES, paragraph(LONG), table(["Product", "Units"], [["Pens", "5"]])))
    )
    # When collected / Then table A has the caption; table B does not
    first, second = contexts(data)
    assert first.caption == "Table 1. Sales by region"
    assert "Table 1" not in all_text(second)


def test_footnote_markers_and_note_words() -> None:
    """FR-123: footnotes are the lines right below starting with a marker or Note:/Source: …"""
    # Given several footnote lines below the table, then a paragraph
    data = make_pdf(
        Page(blocks=(SALES, paragraph("* Provisional."), paragraph("a) Restated."), paragraph("Fuente: INE."), paragraph(LONG)))
    )
    # When collected / Then every marked line is a footnote and the paragraph is `after`
    (context,) = contexts(data)
    assert context.footnotes == "* Provisional.\na) Restated.\nFuente: INE."
    assert context.after == LONG.strip()


# --- FR-124: what never counts ---------------------------------------------------------------------


def test_other_column_running_header_and_page_number_never_count() -> None:
    """VC-127 (FR-124): unrelated text in the other column, a running header and a page number →
    none of them in any field."""
    # Given a 3-page PDF: the same bold running header and a page number on every page, and on
    # page 2 a two-column layout with the table in the right column
    running = "ACME Corp. Annual Report"
    data = make_pdf(
        Page(blocks=(paragraph(LONG),), top_line=running, bottom_line="1"),
        Page(
            blocks=(paragraph("Unrelated left column text about strategy."),),
            right=(paragraph("Table 1. Sales"), SALES, paragraph("Note: In millions.")),
            top_line=running,
            bottom_line="2",
        ),
        Page(blocks=(paragraph(LONG),), top_line=running, bottom_line="3"),
    )
    # When collected
    (context,) = contexts(data)
    # Then only the right column's own text is context
    assert context.caption == "Table 1. Sales"
    assert context.footnotes == "Note: In millions."
    text = all_text(context)
    assert "Unrelated" not in text and running not in text
    assert context.section == "" and context.after == ""


def test_page_number_under_the_table_is_not_after() -> None:
    """FR-124: a bare page number below the table is never `after`, even in a 1-page PDF."""
    # Given a table with a page number right under it, in the same column
    data = make_pdf(Page(blocks=(paragraph(LONG), SALES), bottom_line="7"))
    # When collected / Then `after` stays empty
    (context,) = contexts(data)
    assert context.after == ""


def test_one_page_pdf_keeps_its_context() -> None:
    """VC-169 (FR-121, FR-124): a 1-page PDF with a caption, a paragraph and a large image → the
    caption and paragraph are context (repetition rules need 3 pages)."""
    # Given a single page with a header line, a paragraph, a caption, a table and a large image
    data = make_pdf(
        Page(
            blocks=(paragraph("Sales grew everywhere."), paragraph("Table 1. Sales"), SALES),
            images=(image_covering(0.1),),
            top_line="Quarterly Review",
        )
    )
    # When collected / Then caption and paragraph are found; the single-page header line counts
    (context,) = contexts(data)
    assert context.caption == "Table 1. Sales"
    assert context.before == "Sales grew everywhere."
    assert context.section == "Quarterly Review"


def test_header_line_repeated_on_four_pages_is_not_section() -> None:
    """VC-169 (FR-124): a 4-page PDF with the same header line on every page → not counted."""
    # Given four pages with the same bold header line and a table on page 3
    pages = [Page(blocks=(paragraph(LONG),), top_line="Quarterly Review") for _ in range(4)]
    pages[2] = Page(blocks=(paragraph("Table 1. Sales"), SALES), top_line="Quarterly Review")
    # When collected / Then the header line is in no field
    (context,) = contexts(make_pdf(*pages))
    assert "Quarterly Review" not in all_text(context)
    assert context.caption == "Table 1. Sales"


# --- FR-125: multi-page Tables -----------------------------------------------------------------------


def test_multi_page_table_takes_caption_from_first_part_and_footnote_from_last() -> None:
    """VC-128 (FR-125): a table on pages 2–3, caption on page 2 and footnote on page 3 → both
    found; the section is searched back on page 1."""
    # Given a heading on page 1 and a table split over pages 2 and 3
    header = ["Month", "Units", "Returns"]
    rows = [[f"M{n:02d}", str(n), str(2 * n)] for n in range(1, 31)]
    data = make_pdf(
        Page(blocks=(heading("Monthly figures"), paragraph(LONG))),
        Page(blocks=(paragraph("Table 7. Units by month"), table(header, rows[:20]))),
        Page(blocks=(table(header, rows[20:]), paragraph("Source: Sales ledger."), paragraph("Units peaked in M30."))),
    )
    # When collected
    (context,) = contexts(data)
    # Then the first part gives section and caption, the last part footnotes and after
    assert context.section == "Monthly figures"
    assert context.caption == "Table 7. Units by month"
    assert context.footnotes == "Source: Sales ledger."
    assert context.after == "Units peaked in M30."


# --- FR-126: size limits -------------------------------------------------------------------------


def test_context_is_cut_to_the_limits() -> None:
    """VC-129 (FR-126): 5,000 characters of surrounding text → at most 2,000; `section` and
    `caption` intact; `before` and `after` at most 600 each."""
    # Given long text above, below and in a footnote
    above = ("Above text. " * 125).strip()  # 1,500 characters
    below = ("Below text. " * 125).strip()
    note = "(1) " + ("Footnote. " * 200).strip()  # about 2,000 characters
    data = make_pdf(
        Page(blocks=(heading("Sales"), paragraph(above), paragraph("Table 1. Sales by region"), SALES, paragraph(note), paragraph(below)))
    )
    # When collected
    (context,) = contexts(data)
    # Then the total fits and the identifying fields are untouched
    assert len("".join(astuple(context))) <= MAX_CONTEXT_CHARS
    assert context.section == "Sales"
    assert context.caption == "Table 1. Sales by region"
    assert len(context.before) <= MAX_PARAGRAPH_CHARS and len(context.after) <= MAX_PARAGRAPH_CHARS
    assert context.footnotes.startswith("(1) Footnote.")


def test_short_context_is_not_cut() -> None:
    """FR-126: `before` is cut to 600 characters only when longer."""
    # Given a 700-character paragraph above
    above = "x" * 10 + (" word" * 138)
    data = make_pdf(Page(blocks=(paragraph(above), SALES)))
    # When collected / Then it is cut to exactly 600 characters
    (context,) = contexts(data)
    assert context.before == above[:MAX_PARAGRAPH_CHARS]


# --- The sample PDFs -------------------------------------------------------------------------------


@pytest.mark.parametrize("name", [samples.ACME_FILE, samples.INFORME_FILE])
def test_every_sample_table_has_a_caption(name: str) -> None:
    """Iteration 3 criterion: the sample PDFs' Tables each get a non-empty caption."""
    # Given a committed sample PDF / When its contexts are collected / Then each has a caption
    found = contexts((ROOT / "data" / "sample_pdfs" / name).read_bytes())
    assert found and all(context.caption for context in found)
    prefix = "Table" if name == samples.ACME_FILE else "Cuadro"
    assert all(context.caption.startswith(prefix) for context in found)
