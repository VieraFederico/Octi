"""Generate the two sample PDFs in `data/sample_pdfs/` (spec 01 FR-156; D-070, D-107).

Usage (from the project root):  python -m scripts.make_sample_pdfs

- `acme-annual-report-2023.pdf` (English): currency, percent, parentheses negatives, `n/a`, a
  two-row header with merged cells, footnotes, a two-column page with an embedded image, a table
  continued over two pages, and the tables of spec 03's test questions (gross and net revenue,
  R&D expenses, regional sales without a national row).
- `informe-regional-2024.pdf` (Spanish): `1.234,5` decimals, section titles, `Cuadro N` captions and
  the same regions as ACME (an entity shared by both PDFs).

Every table's data lives in the module-level constants below; the PDFs are drawn from them, and
tests and the evaluation import them (e.g. `from scripts.make_sample_pdfs import ACME_INCOME`), so
expected values cannot drift from what the PDFs show. Output is deterministic: the same PyMuPDF
version writes byte-identical files.

Pages are drawn from HTML with PyMuPDF's Story engine (`Page.insert_htmlbox`), the approach of the
course playground's PDF-tables lesson generator.
"""

import html
from collections.abc import Sequence
from pathlib import Path

import pymupdf

OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "sample_pdfs"
ACME_FILE = "acme-annual-report-2023.pdf"
INFORME_FILE = "informe-regional-2024.pdf"

# --- ACME table data (amounts in USD millions unless stated) -------------------------------------

ACME_YEARS = (2021, 2022, 2023)

# Table 1 — income summary. Net margin = net income / net revenue, in percent.
ACME_INCOME_COLUMNS = ("Revenue (gross)", "Revenue (net)", "Net income", "Net margin")
ACME_INCOME = {
    2021: {"Revenue (gross)": 1290.4, "Revenue (net)": 1204.5, "Net income": 96.3, "Net margin": 8.0},
    2022: {"Revenue (gross)": 1415.8, "Revenue (net)": 1322.0, "Net income": -12.4, "Net margin": -0.9},
    2023: {"Revenue (gross)": 1391.2, "Revenue (net)": 1288.7, "Net income": 103.1, "Net margin": 8.0},
}

# Table 2 — research and development: expenses (USD millions) and staff (people).
ACME_RD_COLUMNS = ("R&D expenses", "R&D staff")
ACME_RD = {
    2021: {"R&D expenses": 84.3, "R&D staff": 310},
    2022: {"R&D expenses": 97.6, "R&D staff": 342},
    2023: {"R&D expenses": 112.9, "R&D staff": 365},
}

# Table 3 — net sales by region (USD millions; each year sums to the net revenue of Table 1) and
# ACME's share of each region's retail market (percent). There is no national row (D-107).
ACME_REGIONAL_NET_SALES = {
    "Patagonia": {2021: 210.3, 2022: 231.7, 2023: 239.8},
    "Cuyo": {2021: 185.2, 2022: 201.4, 2023: 190.6},
    "Pampa": {2021: 498.6, 2022: 545.0, 2023: 520.4},
    "NOA": {2021: 176.9, 2022: 195.3, 2023: 196.2},
    "NEA": {2021: 133.5, 2022: 148.6, 2023: 141.7},
}
ACME_MARKET_SHARE_YEARS = (2022, 2023)
ACME_MARKET_SHARE = {
    "Patagonia": {2022: 12.4, 2023: 13.1},
    "Cuyo": {2022: 9.8, 2023: 9.2},
    "Pampa": {2022: 7.5, 2023: 7.1},
    "NOA": {2022: 11.0, 2023: 11.3},
    "NEA": {2022: 8.9, 2023: 8.5},
}


def _percent_change(old: float | None, new: float | None) -> float | None:
    """The change from `old` to `new` in percent, one decimal; `None` when either is unknown."""
    if old is None or new is None:
        return None
    return round((new / old - 1) * 100, 1)


# Table 4 — employees by department at year end; "Data science" was created in 2023 (n/a in 2022).
ACME_HEADCOUNT_COLUMNS = ("Employees 2022", "Employees 2023", "Change")
_EMPLOYEES = {
    "Engineering": (410, 452),
    "Sales": (285, 271),
    "Operations": (198, 205),
    "Data science": (None, 38),
    "Administration": (96, 91),
}
ACME_HEADCOUNT = {
    department: {"Employees 2022": old, "Employees 2023": new, "Change": _percent_change(old, new)}
    for department, (old, new) in _EMPLOYEES.items()
}

# Table 5 — monthly net sales (USD thousands) and the change versus the previous month (percent).
# Each year's months follow one seasonal pattern and sum exactly to that year's net revenue.
_SEASON = (0.90, 0.85, 0.95, 1.00, 1.02, 0.98, 1.05, 1.00, 0.97, 1.03, 1.08, 1.17)  # sums to 12


def _monthly_net_sales() -> dict[str, dict[str, float | None]]:
    rows: dict[str, dict[str, float | None]] = {}
    previous: float | None = None
    for year in ACME_YEARS:
        total = round(ACME_INCOME[year]["Revenue (net)"] * 1000, 1)
        months = [round(total * weight / 12, 1) for weight in _SEASON[:-1]]
        months.append(round(total - sum(months), 1))  # December absorbs the rounding
        for month, value in enumerate(months, start=1):
            rows[f"{year}-{month:02d}"] = {
                "Net sales (USD thousands)": value,
                "Change vs previous month": _percent_change(previous, value),
            }
            previous = value
    return rows


ACME_MONTHLY = _monthly_net_sales()
ACME_MONTHLY_FIRST_PAGE_ROWS = 30  # the rest continue on the next page

# --- Informe table data (Spanish PDF) ------------------------------------------------------------

INFORME_YEARS = (2022, 2023)

# Cuadro 1 — población por región (miles de habitantes).
INFORME_POPULATION = {
    "Patagonia": {2022: 2876.4, 2023: 2910.8},
    "Cuyo": {2022: 3401.2, 2023: 3428.9},
    "Pampa": {2022: 17230.5, 2023: 17355.1},
    "NOA": {2022: 5912.7, 2023: 5958.3},
    "NEA": {2022: 4301.9, 2023: 4330.2},
}

# Cuadro 2 — mercado laboral 2023 (porcentajes).
INFORME_LABOUR_COLUMNS = ("Tasa de desempleo", "Tasa de empleo")
INFORME_LABOUR = {
    "Patagonia": {"Tasa de desempleo": 6.1, "Tasa de empleo": 44.2},
    "Cuyo": {"Tasa de desempleo": 5.4, "Tasa de empleo": 42.8},
    "Pampa": {"Tasa de desempleo": 7.3, "Tasa de empleo": 45.6},
    "NOA": {"Tasa de desempleo": 8.2, "Tasa de empleo": 39.5},
    "NEA": {"Tasa de desempleo": 7.9, "Tasa de empleo": 37.4},
}

# --- Drawing -------------------------------------------------------------------------------------

PAGE_RECT = pymupdf.paper_rect("a4")
MARGIN = 36
CONTENT_RECT = PAGE_RECT + (MARGIN, MARGIN, -MARGIN, -MARGIN)
GUTTER = 9
CSS = """
body { font-family: sans-serif; font-size: 10pt; }
h1 { font-size: 18pt; }
h2 { font-size: 13pt; }
table { border-collapse: collapse; margin-bottom: 4pt; }
th, td { border: 1px solid black; padding: 2pt 6pt; }
"""
ACME_RUNNING_HEADER = "ACME Corp. - Annual Report 2023"


def _money(value: float) -> str:
    """`$1,204.5`, negatives in parentheses: `$(12.4)`."""
    return f"${value:,.1f}" if value >= 0 else f"$({-value:,.1f})"


def _percent(value: float | None) -> str:
    """`8.0%`, negatives in parentheses: `(0.9%)`, unknown: `n/a`."""
    if value is None:
        return "n/a"
    return f"{value:.1f}%" if value >= 0 else f"({-value:.1f}%)"


def _number(value: float | None, decimals: int = 1) -> str:
    """`1,234.5` (English), unknown: `n/a`."""
    return "n/a" if value is None else f"{value:,.{decimals}f}"


def _european(value: float) -> str:
    """`1.234,5`: dot for thousands, comma for decimals."""
    return f"{value:,.1f}".replace(",", " ").replace(".", ",").replace(" ", ".")


def _european_percent(value: float) -> str:
    """`6,1%`."""
    return f"{_european(value)}%"


def _h(level: int, text: str) -> str:
    return f"<h{level}>{html.escape(text)}</h{level}>"


def _p(text: str) -> str:
    return f"<p>{html.escape(text)}</p>"


def _caption(text: str) -> str:
    return f"<p><b>{html.escape(text)}</b></p>"


def _table(header: Sequence[str], rows: Sequence[Sequence[str]], top: Sequence[tuple[str, int]] = ()) -> str:
    """A ruled table; `top` is an optional row of `(text, columns spanned)` cells above `header`."""
    cells = "".join(f'<th colspan="{span}">{html.escape(text)}</th>' for text, span in top)
    top_row = f"<tr>{cells}</tr>" if top else ""
    head = "<tr>" + "".join(f"<th>{html.escape(cell)}</th>" for cell in header) + "</tr>"
    body = "".join("<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in row) + "</tr>" for row in rows)
    return f"<table>{top_row}{head}{body}</table>"


def _draw(page: pymupdf.Page, rect: pymupdf.Rect, blocks: Sequence[str]) -> None:
    """Draw HTML blocks in `rect`, never shrinking them; a block that does not fit is a bug here."""
    spare_height, _scale = page.insert_htmlbox(rect, "".join(blocks), css=CSS, scale_low=1)
    if spare_height < 0:
        raise ValueError(f"page {page.number + 1}: the content does not fit")


def _new_page(doc: pymupdf.Document, running_header: str = "") -> pymupdf.Page:
    """A new A4 page with the running header and its page number in the margins."""
    page = doc.new_page(width=PAGE_RECT.width, height=PAGE_RECT.height)
    if running_header:
        page.insert_text((MARGIN, MARGIN - 12), running_header, fontsize=8)
    page.insert_text((PAGE_RECT.width / 2, PAGE_RECT.height - MARGIN + 18), str(page.number + 1), fontsize=8)
    return page


def _pixmap(shade: int) -> pymupdf.Pixmap:
    """A small gray RGB image, scaled up where it is placed (a stand-in for a chart)."""
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 16, 16), False)
    pixmap.clear_with(shade)
    return pixmap


def _save(doc: pymupdf.Document) -> bytes:
    """Deterministic bytes: no fresh file id, no dates, unused objects removed."""
    doc.set_metadata({})
    return doc.tobytes(garbage=3, deflate=True, no_new_id=True)


def build_acme_pdf() -> bytes:
    """The ACME annual report (English, 5 pages)."""
    years = ACME_YEARS
    with pymupdf.open() as doc:
        # Page 1 — income summary and R&D.
        page = _new_page(doc, ACME_RUNNING_HEADER)
        income_rows = [
            [str(year)]
            + [_money(ACME_INCOME[year][column]) for column in ACME_INCOME_COLUMNS[:3]]
            + [_percent(ACME_INCOME[year]["Net margin"])]
            for year in years
        ]
        rd_rows = [[str(year), _number(ACME_RD[year]["R&D expenses"]), str(ACME_RD[year]["R&D staff"])] for year in years]
        _draw(page, CONTENT_RECT, [
            _h(1, "ACME Corp. Annual Report 2023"),
            _h(2, "1. Financial overview"),
            _p("ACME sells consumer electronics through retail partners in five regions. This section "
               "summarises the results of the last three fiscal years."),
            _caption("Table 1. Income summary, 2021-2023 (USD millions)"),
            _table(["Fiscal year", *ACME_INCOME_COLUMNS], income_rows),
            _p("(1) Net revenue is gross revenue minus returns, discounts and sales taxes."),
            _p("Note: 2022 includes a one-off restructuring charge of USD 85 million."),
            _p("Net revenue fell in 2023 as volumes in Cuyo and Pampa declined, while margins recovered "
               "after the restructuring."),
            _h(2, "2. Research and development"),
            _p("ACME keeps investing in new products. R&D expenses are reported in USD millions and "
               "staff as people at year end."),
            _caption("Table 2. Research and development expenses and staff"),
            _table(["Fiscal year", *ACME_RD_COLUMNS], rd_rows),
            _p("Source: ACME finance department."),
        ])

        # Page 2 — regional sales (two-row header with merged cells, no national row).
        page = _new_page(doc, ACME_RUNNING_HEADER)
        regional_rows = [
            [region]
            + [_number(ACME_REGIONAL_NET_SALES[region][year]) for year in years]
            + [_percent(ACME_MARKET_SHARE[region][year]) for year in ACME_MARKET_SHARE_YEARS]
            for region in ACME_REGIONAL_NET_SALES
        ]
        _draw(page, CONTENT_RECT, [
            _h(2, "3. Regional sales"),
            _p("Net sales are broken down by the region of the retail partner. Market share is ACME's "
               "share of each region's consumer electronics retail market."),
            _caption("Table 3. Net sales by region (USD millions) and market share"),
            _table(
                ["", *[str(year) for year in years], *[str(year) for year in ACME_MARKET_SHARE_YEARS]],
                regional_rows,
                top=(("Region", 1), ("Net sales", len(years)), ("Market share", len(ACME_MARKET_SHARE_YEARS))),
            ),
            _p("* Market share figures come from an industry panel and were not collected for 2021."),
            _p("Pampa remains the largest region by sales, while Patagonia grew fastest over the period."),
        ])

        # Page 3 — two columns: outlook text and an image on the left, the workforce table on the right.
        page = _new_page(doc, ACME_RUNNING_HEADER)
        middle = CONTENT_RECT.x0 + CONTENT_RECT.width / 2
        left = pymupdf.Rect(CONTENT_RECT.x0, CONTENT_RECT.y0, middle - GUTTER, CONTENT_RECT.y0 + 130)
        right = pymupdf.Rect(middle + GUTTER, CONTENT_RECT.y0, CONTENT_RECT.x1, CONTENT_RECT.y1)
        _draw(page, left, [
            _h(2, "4. Strategy and outlook"),
            _p("For 2024 ACME expects modest growth in Patagonia and NOA, supported by two new retail "
               "partners. Cost discipline continues after the 2022 restructuring."),
            _p("The chart below shows the regional mix of net sales in 2023. It is an image and its "
               "numbers are not part of any table."),
        ])
        page.insert_image(pymupdf.Rect(CONTENT_RECT.x0, CONTENT_RECT.y0 + 140, middle - GUTTER, CONTENT_RECT.y0 + 320), pixmap=_pixmap(170))
        headcount_rows = [
            [department]
            + [_number(values[column], 0) for column in ACME_HEADCOUNT_COLUMNS[:2]]
            + [_percent(values["Change"])]
            for department, values in ACME_HEADCOUNT.items()
        ]
        _draw(page, right, [
            _h(2, "5. Workforce"),
            _p("Employees are counted at the end of each year, in full-time equivalents."),
            _caption("Table 4. Employees by department"),
            _table(["Department", *ACME_HEADCOUNT_COLUMNS], headcount_rows),
            _p("Note: the Data science department was created in 2023."),
        ])

        # Pages 4-5 — monthly net sales, continued on the next page with the header repeated.
        month_rows = [
            [month, _number(values["Net sales (USD thousands)"]), _percent(values["Change vs previous month"])]
            for month, values in ACME_MONTHLY.items()
        ]
        monthly_header = ["Month", "Net sales (USD thousands)", "Change vs previous month"]
        first, rest = month_rows[:ACME_MONTHLY_FIRST_PAGE_ROWS], month_rows[ACME_MONTHLY_FIRST_PAGE_ROWS:]
        page = _new_page(doc, ACME_RUNNING_HEADER)
        _draw(page, CONTENT_RECT, [
            _h(2, "6. Monthly sales"),
            _p("Monthly net sales are reported in USD thousands; the twelve months of each year add up "
               "to that year's net revenue in Table 1."),
            _caption("Table 5. Monthly net sales, January 2021 to December 2023"),
            _table(monthly_header, first),
        ])
        page = _new_page(doc, ACME_RUNNING_HEADER)
        _draw(page, CONTENT_RECT, [
            _table(monthly_header, rest),
            _p("Source: ACME sales ledger, unaudited monthly figures."),
            _p("December is the strongest month every year because of holiday sales."),
        ])
        return _save(doc)


def build_informe_pdf() -> bytes:
    """The regional report (Spanish, 1 page)."""
    years = INFORME_YEARS
    with pymupdf.open() as doc:
        page = _new_page(doc)
        population_rows = [[region] + [_european(INFORME_POPULATION[region][year]) for year in years] for region in INFORME_POPULATION]
        labour_rows = [[region] + [_european_percent(INFORME_LABOUR[region][c]) for c in INFORME_LABOUR_COLUMNS] for region in INFORME_LABOUR]
        _draw(page, CONTENT_RECT, [
            _h(1, "Informe Regional 2024"),
            _p("Este informe resume indicadores demográficos y laborales de las cinco regiones del país."),
            _h(2, "1. Población"),
            _p("La población se expresa en miles de habitantes a mitad de cada año."),
            _caption("Cuadro 1. Población por región (miles de habitantes)"),
            _table(["Región", *[str(year) for year in years]], population_rows),
            _p("Fuente: Instituto Nacional de Estadística, proyecciones de población."),
            _h(2, "2. Mercado laboral"),
            _p("Las tasas se calculan sobre la población de 14 años y más, promedio del año 2023."),
            _caption("Cuadro 2. Indicadores del mercado laboral por región, 2023"),
            _table(["Región", *INFORME_LABOUR_COLUMNS], labour_rows),
            _p("Nota: la tasa de empleo es el porcentaje de ocupados sobre la población total."),
        ])
        return _save(doc)


def write_sample_pdfs(out_dir: Path = OUT_DIR) -> list[Path]:
    """Write both sample PDFs into `out_dir` (created if needed) and return their paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = [out_dir / ACME_FILE, out_dir / INFORME_FILE]
    for path, data in zip(paths, (build_acme_pdf(), build_informe_pdf())):
        path.write_bytes(data)
    return paths


if __name__ == "__main__":
    for written in write_sample_pdfs():
        print(f"wrote {written.relative_to(OUT_DIR.parents[1])}")
