"""The sample PDFs and their generator (spec 01 FR-156; D-070, D-107): both PDFs are written, extract
the same way every time, contain the hard cases and the test-question tables, and their extracted
values equal the generator's module-level constants (spec 03 computes expected answers from them)."""

from pathlib import Path

import pymupdf
import pytest

from agents.ingestion.pdf.tables import document_sha, extract_tables
from agents.ingestion.schemas import ExtractedTable
from scripts import make_sample_pdfs as samples

ROOT = Path(__file__).resolve().parents[2]
COMMITTED = ROOT / "data" / "sample_pdfs"


def extract_file(path: Path) -> list[ExtractedTable]:
    """The Tables of a PDF file on disk."""
    data = path.read_bytes()
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        return extract_tables(doc, document_sha(data))


def shape(tables: list[ExtractedTable]) -> list[tuple[list[str], int, list[int]]]:
    """What must not change between runs: column names, row counts and pages of each Table."""
    return [(t.columns, len(t.frame), t.pages) for t in tables]


def by_first_column(tables: list[ExtractedTable], name: str) -> ExtractedTable:
    """The one Table whose first column has this name."""
    (found,) = [t for t in tables if t.columns and t.columns[0] == name]
    return found


def by_column(tables: list[ExtractedTable], name: str) -> ExtractedTable:
    """The one Table that has a column with this name."""
    (found,) = [t for t in tables if name in t.columns]
    return found


@pytest.fixture(scope="module")
def acme(tmp_path_factory: pytest.TempPathFactory) -> list[ExtractedTable]:
    """The Tables of a freshly generated ACME PDF."""
    out = tmp_path_factory.mktemp("acme")
    samples.write_sample_pdfs(out)
    return extract_file(out / samples.ACME_FILE)


@pytest.fixture(scope="module")
def informe(tmp_path_factory: pytest.TempPathFactory) -> list[ExtractedTable]:
    """The Tables of a freshly generated Informe PDF."""
    out = tmp_path_factory.mktemp("informe")
    samples.write_sample_pdfs(out)
    return extract_file(out / samples.INFORME_FILE)


# --- Generation is repeatable --------------------------------------------------------------------


def test_running_the_script_twice_gives_the_same_tables(tmp_path: Path) -> None:
    """VC-161 (FR-156): running the script twice → both PDFs exist and extract the same Tables."""
    # Given two runs of the generator into two folders
    first, second = tmp_path / "first", tmp_path / "second"
    samples.write_sample_pdfs(first)
    samples.write_sample_pdfs(second)
    # When both outputs are extracted / Then both PDFs exist and their Tables have the same shape
    for name in (samples.ACME_FILE, samples.INFORME_FILE):
        assert (first / name).is_file() and (second / name).is_file()
        assert shape(extract_file(first / name)) == shape(extract_file(second / name))
        assert (first / name).read_bytes() == (second / name).read_bytes()  # deterministic output


def test_committed_pdfs_match_the_generator(tmp_path: Path) -> None:
    """FR-156: the committed sample PDFs extract exactly like a fresh run of the script."""
    # Given a fresh run / When the committed files are extracted / Then the same Tables
    samples.write_sample_pdfs(tmp_path)
    for name in (samples.ACME_FILE, samples.INFORME_FILE):
        assert shape(extract_file(COMMITTED / name)) == shape(extract_file(tmp_path / name))


# --- ACME: hard cases (D-070) and test-question tables (D-107) -----------------------------------


def test_acme_has_every_table_on_its_pages(acme: list[ExtractedTable]) -> None:
    """VC-161: the ACME PDF has the six intended Tables, readable, with the multi-page one on 4–5."""
    # Given the ACME Tables / Then their pages are as designed and none is unreadable
    assert [t.pages for t in acme] == [[1], [1], [2], [3], [4, 5]]
    assert not any(t.unreadable for t in acme)


def test_acme_income_table_has_gross_and_net_revenue(acme: list[ExtractedTable]) -> None:
    """VC-161 (D-107): the income table has "Revenue (gross)" and "Revenue (net)"; currency,
    parentheses negatives and percent are cleaned to the constants."""
    # Given the income Table
    income = by_column(acme, "Revenue (gross)")
    # Then its columns, values and hints equal the generator's constants
    assert income.columns == ["Fiscal year", *samples.ACME_INCOME_COLUMNS]
    assert income.frame["Fiscal year"].tolist() == list(samples.ACME_YEARS)
    for column in samples.ACME_INCOME_COLUMNS:
        assert income.frame[column].tolist() == [samples.ACME_INCOME[year][column] for year in samples.ACME_YEARS]
    assert income.hints["Revenue (net)"] == ["currency: $"]
    assert income.hints["Net margin"] == ["percent"]
    assert min(income.frame["Net income"]) < 0  # written as $(12.4)


def test_acme_rd_table(acme: list[ExtractedTable]) -> None:
    """VC-161 (D-107): the R&D expenses table by year equals its constant."""
    # Given the R&D Table / Then the yearly values equal the constants
    rd = by_column(acme, "R&D expenses")
    assert rd.columns == ["Fiscal year", *samples.ACME_RD_COLUMNS]
    assert rd.frame["Fiscal year"].tolist() == list(samples.ACME_YEARS)
    for column in samples.ACME_RD_COLUMNS:
        assert rd.frame[column].tolist() == [samples.ACME_RD[year][column] for year in samples.ACME_YEARS]


def test_acme_regional_table_has_merged_header_and_no_national_row(acme: list[ExtractedTable]) -> None:
    """VC-161 (D-070, D-107): a two-row merged-cell header; the regions only, no national row."""
    # Given the regional Table
    regional = by_column(acme, "Net sales / 2021")
    # Then the merged header was flattened and every value equals the constants
    years = samples.ACME_YEARS
    share_years = samples.ACME_MARKET_SHARE_YEARS
    assert regional.columns == [
        "Region",
        *[f"Net sales / {year}" for year in years],
        *[f"Market share / {year}" for year in share_years],
    ]
    assert regional.row_headers == list(samples.ACME_REGIONAL_NET_SALES)
    assert not any(word in label.lower() for label in regional.row_headers for word in ("national", "total"))
    for year in years:
        column = regional.frame[f"Net sales / {year}"].tolist()
        assert column == [samples.ACME_REGIONAL_NET_SALES[region][year] for region in samples.ACME_REGIONAL_NET_SALES]
    for year in share_years:
        column = regional.frame[f"Market share / {year}"].tolist()
        assert column == [samples.ACME_MARKET_SHARE[region][year] for region in samples.ACME_MARKET_SHARE]


def test_acme_regional_sales_add_up_to_net_revenue() -> None:
    """D-107: the constants agree with each other, so multi-table answers are consistent."""
    # Given the regional and income constants / Then each year's regions sum to the net revenue
    for year in samples.ACME_YEARS:
        total = sum(sales[year] for sales in samples.ACME_REGIONAL_NET_SALES.values())
        assert total == pytest.approx(samples.ACME_INCOME[year]["Revenue (net)"])


def test_acme_headcount_table_on_the_two_column_page(acme: list[ExtractedTable]) -> None:
    """VC-161 (D-070): the right-column table of the two-column page, with `n/a` and negatives."""
    # Given the headcount Table / Then its values equal the constants (n/a → missing)
    headcount = by_first_column(acme, "Department")
    assert headcount.pages == [3]
    assert headcount.row_headers == list(samples.ACME_HEADCOUNT)
    for column in samples.ACME_HEADCOUNT_COLUMNS:
        values = headcount.frame[column].tolist()
        expected = [samples.ACME_HEADCOUNT[department][column] for department in samples.ACME_HEADCOUNT]
        assert [None if v != v else v for v in values] == expected  # NaN → None


def test_acme_monthly_table_spans_two_pages_and_sums_to_the_year(acme: list[ExtractedTable]) -> None:
    """VC-161 (D-070): the multi-page table is one Table with every month; months sum to the year."""
    # Given the monthly Table
    monthly = by_first_column(acme, "Month")
    # Then it has 36 rows over pages 4–5 and its values equal the constants
    assert monthly.pages == [4, 5]
    assert monthly.frame["Month"].tolist() == list(samples.ACME_MONTHLY)
    sales = monthly.frame["Net sales (USD thousands)"].tolist()
    assert sales == [row["Net sales (USD thousands)"] for row in samples.ACME_MONTHLY.values()]
    change = [None if v != v else v for v in monthly.frame["Change vs previous month"].tolist()]
    assert change == [row["Change vs previous month"] for row in samples.ACME_MONTHLY.values()]
    for year in samples.ACME_YEARS:
        year_total = sum(row["Net sales (USD thousands)"] for month, row in samples.ACME_MONTHLY.items() if month.startswith(str(year)))
        assert year_total == pytest.approx(samples.ACME_INCOME[year]["Revenue (net)"] * 1000)


def test_acme_has_an_image_on_a_text_page() -> None:
    """D-070: one embedded image, reported by the FR-121 rule (not a logo, not tiny)."""
    from agents.ingestion.pdf.document import reported_image_pages

    # Given the committed ACME PDF / Then exactly the two-column page is reported
    with pymupdf.open(COMMITTED / samples.ACME_FILE) as doc:
        assert reported_image_pages(doc) == [3]


# --- Informe: Spanish, European decimals, shared entities ----------------------------------------


def test_informe_tables_use_european_decimals(informe: list[ExtractedTable]) -> None:
    """VC-161 (D-070): `1.234,5` values parse to the constants; percent columns are marked."""
    # Given the Informe Tables
    population, labour = informe
    # Then the population and labour values equal the constants
    years = samples.INFORME_YEARS
    assert population.columns == ["Región", *[str(year) for year in years]]
    for year in years:
        assert population.frame[str(year)].tolist() == [samples.INFORME_POPULATION[r][year] for r in samples.INFORME_POPULATION]
    assert labour.columns == ["Región", *samples.INFORME_LABOUR_COLUMNS]
    for column in samples.INFORME_LABOUR_COLUMNS:
        assert labour.frame[column].tolist() == [samples.INFORME_LABOUR[r][column] for r in samples.INFORME_LABOUR]
        assert labour.hints[column] == ["percent"]


def test_informe_shares_its_regions_with_acme(informe: list[ExtractedTable], acme: list[ExtractedTable]) -> None:
    """D-070, D-107: an entity shared across the two PDFs, for multi-PDF questions."""
    # Given the regions of both PDFs / Then the ACME regions all appear in the Informe
    regional = by_column(acme, "Net sales / 2021")
    assert set(regional.row_headers) <= set(informe[0].row_headers)
