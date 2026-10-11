"""Cells become exact column names and typed data without reading a PDF (spec 01)."""

import pandas as pd
import pytest

from agents.ingestion.pdf.cleaning import build_dataframe, clean_column, flatten_headers, row_headers


def test_merged_header_levels_keep_their_measure_and_year() -> None:
    """VC-112: merged Revenue and Costs headings keep the years under each measure."""
    # Given two marked header rows with real horizontal coordinates
    rows = [["Region", "Revenue", None, "Costs", None], ["", "2023", "2024", "2023", "2024"]]
    columns = [(0, 10), (10, 20), (20, 30), (30, 40), (40, 50)]
    spans = [[(0, 10), (10, 30), None, (30, 50), None], columns]
    # When the marked rows are flattened
    names = flatten_headers(rows, spans, columns)
    # Then every year retains its measure
    assert names == ["Region", "Revenue / 2023", "Revenue / 2024", "Costs / 2023", "Costs / 2024"]


@pytest.mark.parametrize("last", ["", None])
def test_uncovered_header_position_does_not_copy_the_left_label(last: str | None) -> None:
    """VC-114: an empty cell, or a None outside the left box, stays unnamed."""
    # Given Total ends before the second column
    rows = [["Total", last]]
    columns = [(0, 10), (10, 20)]
    spans = [[(0, 10), (10, 20) if last == "" else None]]
    # When flattened / Then only the first column is Total
    assert flatten_headers(rows, spans, columns) == ["Total", "Column 2"]


def test_repeated_and_empty_headers_receive_unique_flat_names() -> None:
    """VC-115: duplicates get suffixes, blanks get positions, and line breaks collapse."""
    # Given a single header row
    rows = [["Total", "Total", "", "Total\nrevenue"]]
    columns = [(0, 10), (10, 20), (20, 30), (30, 40)]
    # When flattened / Then all four names are usable as exact column names
    assert flatten_headers(rows, [columns], columns) == ["Total", "Total (2)", "Column 3", "Total revenue"]


def test_repeated_header_levels_and_whitespace_are_removed() -> None:
    """FR-113.3–4: equal consecutive levels contribute only one normalized part."""
    # Given three marked levels, some empty or repeated
    rows = [[" Revenue\n total ", ""], ["Revenue total", ""], ["2023", ""]]
    columns = [(0, 10), (10, 20)]
    # When flattened / Then repeated levels and blanks do not add separators
    assert flatten_headers(rows, [columns] * 3, columns) == ["Revenue total / 2023", "Column 2"]


def test_merge_over_three_columns_uses_the_original_cell_span() -> None:
    """FR-113.2: covered positions have no boxes, so the original merged box supplies the span."""
    # Given one heading spanning three columns, followed by a genuinely empty cell
    rows = [["Measure", None, None, ""]]
    columns = [(0, 10), (10, 20), (20, 30), (30, 40)]
    # When flattened / Then only positions covered by the box inherit the heading
    assert flatten_headers(rows, [[(0, 30), None, None, (30, 40)]], columns) == [
        "Measure", "Measure (2)", "Measure (3)", "Column 4"
    ]


def test_generated_suffixes_do_not_make_column_names_repeat() -> None:
    """FR-113.4: uniqueness also holds when a literal heading already contains a suffix."""
    # Given literal names that can collide with generated suffixes
    rows = [["Total", "Total (2)", "Total", "Total"]]
    columns = [(0, 10), (10, 20), (20, 30), (30, 40)]
    # When flattened / Then suffixes advance to the next unused name
    assert flatten_headers(rows, [columns], columns) == ["Total", "Total (2)", "Total (3)", "Total (4)"]


def test_missing_values_make_an_otherwise_whole_column_float64() -> None:
    """VC-118: 1, n/a, em dash, 3 become float64 with two missing values."""
    # Given whole numbers and specified missing markers
    values = ["1", "n/a", "—", "3"]
    # When cleaned
    column, hints = clean_column(values)
    # Then missing values are real gaps, not strings
    pd.testing.assert_series_equal(column, pd.Series([1.0, float("nan"), float("nan"), 3.0]))
    assert hints == []


@pytest.mark.parametrize("missing", [None, "", "  ", "n/a", "N/A", "-", "—", "–", ".."])
def test_every_specified_missing_marker_becomes_nan_in_a_numeric_column(missing: str | None) -> None:
    """FR-115 / VC-118: every listed empty or missing marker is recognized."""
    # Given a measure with one gap / When cleaned
    column, hints = clean_column(["1", missing])
    # Then the gap is missing and the column is float64
    assert column.dtype == "float64"
    assert column.iloc[0] == 1
    assert pd.isna(column.iloc[1])
    assert hints == []


def test_whole_numbers_without_gaps_are_int64() -> None:
    """VC-118: 1, 2, 3 become int64."""
    # Given three whole numbers / When cleaned
    column, hints = clean_column(["1", "2", "3"])
    # Then integer arithmetic is available without changing values
    pd.testing.assert_series_equal(column, pd.Series([1, 2, 3], dtype="int64"))
    assert hints == []


@pytest.mark.parametrize(
    ("cell", "number", "dtype", "hints"),
    [
        ("$1,204.5", 1204.5, "float64", ["currency: $"]),
        ("(12.4)", -12.4, "float64", []),
        ("−3", -3, "int64", []),
        ("8.0%", 8, "int64", ["percent"]),
        ("1,204(1)", 1204, "int64", []),
        ("US$ 7", 7, "int64", ["currency: US$"]),
        ("9(a)", 9, "int64", []),
        ("9*", 9, "int64", []),
        ("9¹²", 9, "int64", []),
        ("€ 7", 7, "int64", ["currency: €"]),
        ("£7", 7, "int64", ["currency: £"]),
        ("ARS 7", 7, "int64", ["currency: ARS"]),
        ("($1,204.5)(a)", -1204.5, "float64", ["currency: $"]),
    ],
)
def test_number_decorations_preserve_the_written_amount_and_symbol(
    cell: str, number: int | float, dtype: str, hints: list[str]
) -> None:
    """VC-119 / FR-116: decorations are removed; percent values are not divided by 100."""
    # Given a written amount / When its column is cleaned
    column, actual_hints = clean_column([cell])
    # Then its exact meaning is preserved as data plus hints
    assert column.iloc[0] == number
    assert column.dtype == dtype
    assert actual_hints == hints


@pytest.mark.parametrize(
    ("values", "expected"),
    [(["1.234,5", "2.000"], [1234.5, 2000.0]), (["2.000", "1.234,5"], [2000.0, 1234.5])],
)
def test_european_decimal_evidence_applies_to_every_cell_in_the_column(
    values: list[str], expected: list[float]
) -> None:
    """VC-120: 1.234,5 settles the column style, so 2.000 means 2000."""
    # Given one decisive value, before or after an otherwise ambiguous value
    # When cleaned
    column, hints = clean_column(values)
    # Then all rows use the same European style
    pd.testing.assert_series_equal(column, pd.Series(expected))
    assert hints == []


def test_ambiguous_dot_defaults_to_english_decimal_style() -> None:
    """VC-120: without decisive evidence, 1.234 is an English decimal."""
    # Given an ambiguous dot / When cleaned
    column, hints = clean_column(["1.234"])
    # Then it is not guessed to be a thousands separator
    assert column.tolist() == [1.234]
    assert column.dtype == "float64"
    assert hints == []


@pytest.mark.parametrize(
    ("values", "expected"),
    [(["12,5", "2.000"], [12.5, 2000.0]), (["1,234", "2,000"], [1234, 2000]),
     (["0.5", "0"], [0.5, 0.0]), (["0,5", "0"], [0.5, 0.0])],
)
def test_decimal_style_distinguishes_fractional_evidence_from_ambiguous_grouping(
    values: list[str], expected: list[int | float]
) -> None:
    """FR-116: short comma fractions settle European style; three-digit commas default to English."""
    # Given consistently written amounts / When cleaned
    column, hints = clean_column(values)
    # Then punctuation is interpreted once for the column
    assert column.tolist() == expected
    assert hints == []


@pytest.mark.parametrize(
    "values",
    [
        ["12", "abc"], ["007", "012"], ["$007", "$12"],
        ["$12", "n/a", " abc "], ["8%", "unknown"],
        ["1.234,5", "1,234.5"], ["12,34,567", "1"], ["1.2.3", "4"],
        ["12(foo)", "13"],
    ],
)
def test_one_unparseable_cell_keeps_the_entire_column_exactly_as_written(values: list[str]) -> None:
    """VC-121 / FR-117: text, codes or invalid separator grammar prevent partial conversion."""
    # Given a column with at least one value that does not parse under the chosen style
    original = list(values)
    # When cleaned
    column, hints = clean_column(values)
    # Then every original cell stays text, with no numeric hints
    pd.testing.assert_series_equal(column, pd.Series(original, dtype=object))
    assert values == original
    assert hints == []


def test_large_whole_number_does_not_round_through_a_float() -> None:
    """FR-117: an exact whole number within int64 remains exact, even above float's integer precision."""
    # Given a valid int64 whose last digit would be lost by float conversion / When cleaned
    column, hints = clean_column(["9007199254740993"])
    # Then the integer remains exact
    assert column.iloc[0] == 9007199254740993
    assert column.dtype == "int64"
    assert hints == []


@pytest.mark.parametrize("amount", ["9223372036854775808", "-9223372036854775809"])
def test_whole_column_outside_int64_range_stays_text(amount: str) -> None:
    """S01-D-007: an unrepresentable whole amount keeps every cell and removes numeric hints."""
    # Given an amount just outside either int64 limit, alongside a valid amount
    values = [f"US$ {amount}", "US$ 7"]
    # When cleaned
    column, hints = clean_column(values)
    # Then the whole column remains exact text, rather than overflowing or rounding
    pd.testing.assert_series_equal(column, pd.Series(values, dtype=object))
    assert hints == []


@pytest.mark.parametrize("amount", ["9223372036854775807", "-9223372036854775808"])
def test_whole_amount_at_int64_limit_is_kept_exact(amount: str) -> None:
    """FR-117 / S01-D-007: both inclusive int64 limits are representable without rounding."""
    # Given a decorated amount at either signed limit / When cleaned
    column, hints = clean_column([f"US$ {amount}"])
    # Then the boundary remains numeric with its currency hint
    assert column.iloc[0] == int(amount)
    assert column.dtype == "int64"
    assert hints == ["currency: US$"]


def test_hints_are_deduplicated_and_keep_their_written_symbols() -> None:
    """VC-122 / FR-118: several decorations contribute distinct first-seen hints."""
    # Given different currency symbols and percent signs in a fully numeric column / When cleaned
    column, hints = clean_column(["US$ 7", "$8", "$9", "10%", "11%"])
    # Then the symbols stay distinct and repeated hints are omitted
    assert column.tolist() == [7, 8, 9, 10, 11]
    assert hints == ["currency: US$", "currency: $", "percent"]


def test_entirely_missing_column_is_float64() -> None:
    """FR-115 / FR-117: a column with only gaps has no whole-number dtype."""
    # Given only missing markers / When cleaned
    column, hints = clean_column([None, "n/a", ""])
    # Then every value is a missing numeric value
    assert column.dtype == "float64"
    assert column.isna().all()
    assert hints == []


def test_dataframe_builder_keeps_labels_and_cleans_each_measure_independently() -> None:
    """VC-117 / VC-122: the frame retains Region and carries percent/currency hints by column name."""
    # Given names already flattened and a rectangular grid of data rows
    names = ["Region", "Revenue", "Growth"]
    rows = [["North", "$1,204.5", "8.0%"], ["South", "$7", "12.5%"]]
    original = [list(row) for row in rows]
    # When built
    frame, hints = build_dataframe(names, rows)
    # Then each measure has its own type and hints; input cells are untouched
    assert frame.columns.tolist() == names
    assert frame["Region"].tolist() == ["North", "South"]
    assert frame["Revenue"].tolist() == [1204.5, 7.0]
    assert frame["Growth"].tolist() == [8.0, 12.5]
    assert frame["Revenue"].dtype == "float64"
    assert frame["Growth"].dtype == "float64"
    assert hints == {"Region": [], "Revenue": ["currency: $"], "Growth": ["percent"]}
    assert rows == original


def test_first_text_column_supplies_row_headers_without_being_removed() -> None:
    """VC-117: North and South become row headers, and Region remains in the frame."""
    # Given a cleaned frame with a label column
    frame = pd.DataFrame({"Region": ["North", "South"], "Total": [1, 2]})
    # When row headers are collected
    labels = row_headers(frame)
    # Then the column stays present
    assert labels == ["North", "South"]
    assert frame["Region"].tolist() == ["North", "South"]


def test_missing_row_labels_are_omitted_without_changing_the_column() -> None:
    """FR-114 / S01-D-006: missing first-column labels do not become row headers."""
    # Given a text column whose original missing markers remain written
    values = ["North", None, "", "n/a", "N/A", "-", "—", "–", "..", "South"]
    frame = pd.DataFrame({"Region": pd.Series(values, dtype=object)})
    # When row headers are collected / Then only actual labels are listed, in order
    assert row_headers(frame) == ["North", "South"]
    assert frame["Region"].tolist() == values


@pytest.mark.parametrize("frame", [pd.DataFrame(), pd.DataFrame({"Year": [2023, 2024], "Region": ["North", "South"]})])
def test_row_headers_do_not_search_beyond_the_first_column(frame: pd.DataFrame) -> None:
    """FR-114: a numeric first column or no column means no row headers."""
    # Given a frame with no first text column / When row headers are requested
    labels = row_headers(frame)
    # Then later text columns are not substituted
    assert labels == []


def test_dataframe_builder_accepts_no_rows() -> None:
    """FR-117: an empty grid can be represented before Iteration 3 drops fake tables."""
    # Given column names but no data / When built
    frame, hints = build_dataframe(["Total"], [])
    # Then the empty frame retains its named column and no hints
    assert frame.shape == (0, 1)
    assert frame["Total"].dtype == "int64"
    assert hints == {"Total": []}
