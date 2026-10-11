"""PyMuPDF behaviour the ingestion design relies on (spec A-101, A-102), checked on a fixture PDF.

If PyMuPDF changes how `find_tables()` reports merged cells, these tests fail before any extraction
test does, and point at the assumption that broke (header flattening, FR-113 step 2, depends on it).
"""

import pymupdf
import pytest

from tests.pdf_fixtures import Page, make_pdf, table

# Top header row: "Region", "Revenue" merged over two columns, and a genuinely empty last cell.
MERGED_HEADER = (("Region", 1), ("Revenue", 2), ("", 1))
HEADER = ("", "2023", "2024", "Total")
ROWS = (("North", "10", "12", "22"), ("South", "7", "9", "16"))


def find_only_table(pdf: bytes) -> tuple[list[list[str | None]], list[list[tuple | None]]]:
    """The cell texts and the cell boxes, row by row, of the single table on page 1."""
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        tables = doc[0].find_tables().tables
        assert len(tables) == 1
        return tables[0].extract(), [row.cells for row in tables[0].rows]


def test_html_colspan_draws_a_merged_cell_that_find_tables_reports() -> None:
    """A-102: a Story HTML table with `colspan` gives one cell whose box spans two columns."""
    # Given a fixture table whose "Revenue" header cell spans two columns
    pdf = make_pdf(Page(blocks=(table(HEADER, ROWS, merged_header=MERGED_HEADER),)))
    # When PyMuPDF finds its table
    texts, boxes = find_only_table(pdf)
    # Then the table keeps all 4 columns, and "Revenue"'s box ends where column 3 ends
    assert [len(row) for row in texts] == [4, 4, 4, 4]
    revenue_box, column_3_box = pymupdf.Rect(boxes[0][1]), pymupdf.Rect(boxes[1][2])
    assert revenue_box.x0 == pytest.approx(pymupdf.Rect(boxes[1][1]).x0)
    assert revenue_box.x1 == pytest.approx(column_3_box.x1)


def test_covered_position_is_none_and_empty_cell_is_an_empty_string() -> None:
    """A-101 (VC-114 precondition): a position covered by a merge is `None`; an empty cell is ``."""
    # Given the same table: column 3 of the top row is covered by "Revenue"; column 4 is empty
    pdf = make_pdf(Page(blocks=(table(HEADER, ROWS, merged_header=MERGED_HEADER),)))
    # When PyMuPDF extracts it
    texts, boxes = find_only_table(pdf)
    # Then the covered position and the empty cell are told apart, in texts and in boxes
    assert texts[0] == ["Region", "Revenue", None, ""]
    assert texts[1] == ["", "2023", "2024", "Total"]
    assert boxes[0][2] is None
    # And every cell that exists, empty or not, has its own box
    real_cells = [box for row in boxes for box in row if box is not None]
    assert len(real_cells) == 4 * 4 - 1
    assert all(pymupdf.Rect(box).width > 0 and pymupdf.Rect(box).height > 0 for box in real_cells)
