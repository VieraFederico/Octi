"""Extracting Tables from PDFs: positions and ids, fake tables, multi-page joins, header rows,
unreadable tables (spec 01 FR-109 … FR-113 step 1, FR-119 table part, FR-122). Fixture PDFs are
built in memory per test (`tests/pdf_fixtures.py`)."""

import hashlib
import logging

import pymupdf
import pytest

from agents.ingestion.pdf.tables import document_sha, extract_tables, make_table_id
from agents.ingestion.schemas import ExtractedTable
from tests.pdf_fixtures import Page, make_pdf, paragraph, table, text_page


def extract(data: bytes) -> list[ExtractedTable]:
    """Extract the Tables of fixture PDF bytes, with the real document hash."""
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        return extract_tables(doc, document_sha(data))


def month_rows(first: int, last: int) -> list[list[str]]:
    """Data rows `M01 | 1 | 2` … : a text label and two plain numbers per row."""
    return [[f"M{n:02d}", str(n), str(n * 2)] for n in range(first, last + 1)]


MONTH_HEADER = ["Month", "Units", "Returns"]


# --- table_id (D-048) ----------------------------------------------------------------------------


def test_document_sha_is_the_full_sha256_of_the_bytes() -> None:
    """§7 table_id: the document hash is the SHA-256 of the PDF bytes, in hex."""
    # Given some bytes / When hashed / Then the full hex digest
    assert document_sha(b"pdf bytes") == hashlib.sha256(b"pdf bytes").hexdigest()


def test_table_id_uses_16_hex_characters_page_and_position() -> None:
    """§7 table_id: `<first 16 hex of the hash>-p<page>-t<position>`."""
    # Given a hash, a page and a position / When the id is made / Then it follows D-048
    sha = "b70e6c0d788efb0a" + "f" * 48
    assert make_table_id(sha, 3, 2) == "b70e6c0d788efb0a-p3-t2"


# --- FR-109: every table, its box and position -------------------------------------------------


def test_two_tables_on_a_page_get_positions_from_the_top() -> None:
    """VC-108 (FR-109): a page with two tables → positions 1 and 2, ids `…-p1-t1`, `…-p1-t2`."""
    # Given one page with two tables separated by a paragraph
    data = make_pdf(
        Page(
            blocks=(
                table(["Region", "Sales"], [["North", "10"], ["South", "12"]]),
                paragraph("Between the two tables."),
                table(["Product", "Units"], [["Pens", "5"], ["Ink", "7"]]),
            )
        )
    )
    # When the tables are extracted
    tables = extract(data)
    # Then both are found, top first, with ids from the hash, page and position
    prefix = hashlib.sha256(data).hexdigest()[:16]
    assert [t.table_id for t in tables] == [f"{prefix}-p1-t1", f"{prefix}-p1-t2"]
    assert [t.columns for t in tables] == [["Region", "Sales"], ["Product", "Units"]]
    assert [t.pages for t in tables] == [[1], [1]]
    first_box, second_box = tables[0].parts[0][1], tables[1].parts[0][1]
    assert tables[0].parts[0][0] == 1
    assert first_box[3] <= second_box[1]  # the first table ends above the second


# --- FR-110: fake tables -----------------------------------------------------------------------


def test_fake_tables_are_dropped_and_logged(caplog: pytest.LogCaptureFixture) -> None:
    """VC-109 (FR-110): a 1-column box, a header-only table and a 3×3 table with one filled data
    cell → only the last is kept; the dropped ones appear in DEBUG logs.

    PyMuPDF 1.28.2 does not report a 1-column box as a table at all, so only the header-only table
    reaches the filter; the `< 2 columns` rule stays as a guard (S01-D-010).
    """
    # Given three tables on one page
    data = make_pdf(
        Page(
            blocks=(
                table(["Notes"], [["first"], ["second"]]),
                paragraph("A header without data follows."),
                table(["Region", "Revenue", "Costs"]),
                paragraph("A sparse table follows."),
                table(["A", "B", "C"], [["", "5", ""], ["", "", ""]]),
            )
        )
    )
    # When the tables are extracted with DEBUG logging
    with caplog.at_level(logging.DEBUG, logger="agents.ingestion.pdf.tables"):
        tables = extract(data)
    # Then only the sparse table remains, after the dropped header-only table (position 1)
    assert len(tables) == 1
    assert tables[0].table_id.endswith("-p1-t2")
    assert tables[0].columns == ["A", "B", "C"]
    dropped = [r.getMessage() for r in caplog.records if "Dropped" in r.getMessage()]
    assert dropped == ["Dropped a table on page 1 (position 1): no data row"]


def test_table_without_any_filled_data_cell_is_dropped() -> None:
    """FR-110: data rows whose cells are all empty → dropped."""
    # Given a table with a header and empty data rows only
    data = make_pdf(Page(blocks=(table(["A", "B"], [["5", ""], ["", ""]]), paragraph("x"),
                                 table(["C", "D"], [["", ""], ["", ""]]))))
    # When extracted / Then only the table with a filled data cell remains
    assert [t.columns for t in extract(data)] == [["A", "B"]]


# --- FR-111, FR-112: multi-page joins ------------------------------------------------------------


@pytest.mark.parametrize("repeat_header", [True, False], ids=["header-repeated", "no-header"])
def test_table_split_over_two_pages_is_one_table(repeat_header: bool) -> None:
    """VC-110 (FR-111, FR-112): 30 rows split over pages 2–3, with or without the repeated header
    → one Table, 30 data rows, pages [2, 3], id `…-p2-t1`."""
    # Given a text page, then a table whose rows continue on the next page
    second_header = MONTH_HEADER if repeat_header else ()
    data = make_pdf(
        text_page("Introduction."),
        Page(blocks=(table(MONTH_HEADER, month_rows(1, 20)),)),
        Page(blocks=(table(second_header, month_rows(21, 30)),)),
    )
    # When extracted
    tables = extract(data)
    # Then the two parts are one Table with every data row in order
    assert len(tables) == 1
    joined = tables[0]
    assert joined.pages == [2, 3]
    assert joined.table_id.endswith("-p2-t1")
    assert joined.columns == MONTH_HEADER
    assert len(joined.frame) == 30
    assert joined.frame["Month"].tolist() == [f"M{n:02d}" for n in range(1, 31)]
    assert [page for page, _box in joined.parts] == [2, 3]


def test_three_page_chain_is_one_table() -> None:
    """VC-110 (FR-111): a chain over pages 2, 3 and 4 → `pages == [2, 3, 4]`."""
    # Given a table continuing on two more pages, the header repeated on each
    data = make_pdf(
        text_page("Introduction."),
        Page(blocks=(table(MONTH_HEADER, month_rows(1, 10)),)),
        Page(blocks=(table(MONTH_HEADER, month_rows(11, 20)),)),
        Page(blocks=(table((), month_rows(21, 30)),)),
    )
    # When extracted / Then one Table spans the three pages
    tables = extract(data)
    assert [t.pages for t in tables] == [[2, 3, 4]]
    assert len(tables[0].frame) == 30


def test_next_page_table_with_a_different_header_is_another_table() -> None:
    """VC-111 (FR-111): same column count but a different header → two Tables."""
    # Given a table at the end of page 1 and another, with its own header, at the top of page 2
    data = make_pdf(
        Page(blocks=(table(MONTH_HEADER, month_rows(1, 5)),)),
        Page(blocks=(table(["Product", "Stock", "Orders"], [["Pens", "5", "7"]]),)),
    )
    # When extracted / Then two Tables
    tables = extract(data)
    assert [t.pages for t in tables] == [[1], [2]]


def test_next_page_table_with_another_column_count_is_another_table() -> None:
    """VC-111 (FR-111): a different column count → two Tables, even without a header."""
    # Given a 3-column table on page 1 and a headerless 2-column table on page 2
    data = make_pdf(
        Page(blocks=(table(MONTH_HEADER, month_rows(1, 5)),)),
        Page(blocks=(table((), [["M06", "6"], ["M07", "7"]]),)),
    )
    # When extracted / Then two Tables
    assert [t.pages for t in extract(data)] == [[1], [2]]


def test_only_the_last_table_of_a_page_continues() -> None:
    """FR-111: the join needs the last table on page N; an earlier table there is not joined."""
    # Given page 1 with two tables (the second has 2 columns) and a headerless 3-column table on page 2
    data = make_pdf(
        Page(blocks=(table(MONTH_HEADER, month_rows(1, 3)), paragraph("x"),
                     table(["Product", "Units"], [["Pens", "5"]]))),
        Page(blocks=(table((), month_rows(4, 6)),)),
    )
    # When extracted / Then nothing is joined
    assert [t.pages for t in extract(data)] == [[1], [1], [2]]


# --- FR-113 step 1: header rows ------------------------------------------------------------------


def test_two_row_merged_header_at_pdf_level() -> None:
    """VC-112 (FR-113): `Region | Revenue (merged over 2) | Costs (merged over 2)` over
    `| 2023 | 2024 | 2023 | 2024` → five flattened names; the first data row is `North …`."""
    # Given a table with a two-row header whose top row has merged cells
    data = make_pdf(
        Page(
            blocks=(
                table(
                    ["", "2023", "2024", "2023", "2024"],
                    [["North", "$10", "$12", "4", "5"], ["South", "$11", "$13", "6", "7"]],
                    merged_header=(("Region", 1), ("Revenue", 2), ("Costs", 2)),
                ),
            )
        )
    )
    # When extracted
    (extracted,) = extract(data)
    # Then both header rows are flattened and cleaning ran on the data rows
    assert extracted.columns == ["Region", "Revenue / 2023", "Revenue / 2024", "Costs / 2023", "Costs / 2024"]
    assert extracted.frame.iloc[0].tolist()[0] == "North"
    assert extracted.frame["Revenue / 2023"].tolist() == [10, 11]
    assert str(extracted.frame["Costs / 2024"].dtype) == "int64"
    assert extracted.hints["Revenue / 2023"] == ["currency: $"]
    assert extracted.row_headers == ["North", "South"]
    assert extracted.unreadable is False


def test_bold_numeric_first_row_is_a_header_row() -> None:
    """VC-113 (FR-113): a bold row `Q1 | 1 | 2 | 3` over plain data rows → it is a header row."""
    # Given a bold first row that looks like data, over plain rows
    data = make_pdf(Page(blocks=(table(["Q1", "1", "2", "3"], [["North", "4", "5", "6"], ["South", "7", "8", "9"]]),)))
    # When extracted / Then its cells are the column names
    (extracted,) = extract(data)
    assert extracted.columns == ["Q1", "1", "2", "3"]
    assert len(extracted.frame) == 2


def test_plain_numeric_first_row_is_data() -> None:
    """VC-113 (FR-113): a plain row `Q1 | 1 | 2 | 3` → it is data (no header clue)."""
    # Given a table without a header row
    data = make_pdf(Page(blocks=(table((), [["Q1", "1", "2", "3"], ["Q2", "4", "5", "6"]]),)))
    # When extracted / Then the names fall back to Column N and both rows are data
    (extracted,) = extract(data)
    assert extracted.columns == ["Column 1", "Column 2", "Column 3", "Column 4"]
    assert extracted.frame["Column 1"].tolist() == ["Q1", "Q2"]


def test_empty_header_cell_next_to_total_at_pdf_level() -> None:
    """VC-114 (FR-113): an empty header cell, not covered by a merge, next to `Total` → `Column N`."""
    # Given a header whose last cell is empty
    data = make_pdf(Page(blocks=(table(["Region", "Total", ""], [["North", "5", "6"], ["South", "7", "8"]]),)))
    # When extracted / Then the empty cell does not copy its neighbour's label
    (extracted,) = extract(data)
    assert extracted.columns == ["Region", "Total", "Column 3"]


def test_at_most_three_header_rows() -> None:
    """VC-116 (FR-113): four candidate header rows → at most 3 used."""
    # Given four label rows on top of one data row
    data = make_pdf(
        Page(blocks=(table(["A", "B", "C"], [["x", "y", "z"], ["p", "q", "r"], ["s", "t", "u"], ["North", "1", "2"]]),))
    )
    # When extracted / Then three rows are the header and the fourth stays data
    (extracted,) = extract(data)
    assert extracted.columns == ["A / x / p", "B / y / q", "C / z / r"]
    assert extracted.frame["A / x / p"].tolist() == ["s", "North"]


def test_all_header_looking_table_keeps_one_data_row() -> None:
    """VC-116 (FR-113): a table whose every row looks like a header keeps at least 1 data row."""
    # Given three label-only rows
    data = make_pdf(Page(blocks=(table(["A", "B"], [["c", "d"], ["e", "f"]]),)))
    # When extracted / Then the last row is data
    (extracted,) = extract(data)
    assert extracted.columns == ["A / c", "B / d"]
    assert extracted.frame.values.tolist() == [["e", "f"]]


def test_year_row_under_labels_is_a_header_row() -> None:
    """FR-113 step 1: whole numbers from 1900 to 2100 in a row of labels count as labels."""
    # Given a plain (not bold) year row under the header, then data
    data = make_pdf(Page(blocks=(table(["Region", "Sales", "Sales"], [["", "2023", "2024"], ["North", "10", "12"]]),)))
    # When extracted / Then the year row is a header level
    (extracted,) = extract(data)
    assert extracted.columns == ["Region", "Sales / 2023", "Sales / 2024"]
    assert extracted.frame["Sales / 2023"].tolist() == [10]


# --- FR-119, FR-122: unreadable tables -----------------------------------------------------------


def test_mostly_unreadable_table_is_flagged_and_not_cleaned(monkeypatch: pytest.MonkeyPatch) -> None:
    """VC-123 (FR-119 table part, FR-122): a table whose cells are mostly `�` is flagged unreadable
    and has no DataFrame.

    PyMuPDF's HTML engine cannot draw text that extracts as `�` (S01-D-010), so the cells marked
    `GARBLED` are rewritten as `�` text when PyMuPDF reads them.
    """
    real_extract = pymupdf.table.Table.extract

    def garbled_extract(self: pymupdf.table.Table) -> list[list[str | None]]:
        rows = real_extract(self)
        return [[cell.replace("GARBLED", "��") if cell else cell for cell in row] for row in rows]

    monkeypatch.setattr(pymupdf.table.Table, "extract", garbled_extract)
    # Given a readable table and a table where 4 of 6 filled cells are unreadable
    data = make_pdf(
        Page(
            blocks=(
                table(["Region", "Sales"], [["North", "10"], ["South", "12"]]),
                paragraph("An unreadable table follows."),
                table(["Region", "Sales"], [["GARBLED", "GARBLED"], ["GARBLED", "GARBLED"]]),
            )
        )
    )
    # When extracted
    readable, unreadable = extract(data)
    # Then the second is flagged, never cleaned, and keeps its page and id
    assert readable.unreadable is False and readable.frame is not None
    assert unreadable.unreadable is True
    assert unreadable.frame is None
    assert unreadable.columns == [] and unreadable.row_headers == [] and unreadable.hints == {}
    assert unreadable.pages == [1]
    assert unreadable.table_id.endswith("-p1-t2")


def test_a_few_unreadable_cells_do_not_flag_the_table(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-119 boundary: `�` in fewer than a quarter of the filled cells → an ordinary Table."""
    real_extract = pymupdf.table.Table.extract

    def garbled_extract(self: pymupdf.table.Table) -> list[list[str | None]]:
        return [[cell.replace("GARBLED", "�") if cell else cell for cell in row] for row in real_extract(self)]

    monkeypatch.setattr(pymupdf.table.Table, "extract", garbled_extract)
    # Given 1 unreadable cell among 10 filled cells
    data = make_pdf(Page(blocks=(table(["Region", "Sales"], [["North", "1"], ["South", "2"], ["East", "3"], ["GARBLED", "4"]]),)))
    # When extracted / Then the table is readable and cleaned
    (extracted,) = extract(data)
    assert extracted.unreadable is False
    assert extracted.frame["Sales"].tolist() == [1, 2, 3, 4]


def test_pdf_without_tables_gives_an_empty_list() -> None:
    """FR-142 precondition: a PDF with text and no tables → no Tables."""
    # Given a text-only PDF / When extracted / Then nothing
    assert extract(make_pdf(text_page("Only prose here."))) == []
