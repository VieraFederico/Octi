"""Turn marked header rows and cell text into clean tabular data (FR-113.2–4, FR-114–118).

Pure functions: no PDF, filesystem or model calls. Header detection belongs to tables.py;
this module receives already marked header rows and rectangular data rows.
"""

import re
from decimal import Decimal

import pandas as pd
from pandas.api.types import is_numeric_dtype

MISSING_VALUES = {"", "n/a", "N/A", "-", "—", "–", ".."}
INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1
DECORATION = re.compile(r"US\$|ARS|\$|€|£|%")
FOOTNOTE = re.compile(r"(?<=[0-9)])\s*(?:\([0-9]+\)|\([a-zA-Z]\)|\*+|[⁰¹²³⁴⁵⁶⁷⁸⁹]+)$")
ENGLISH_NUMBER = re.compile(r"[+-]?(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]+)?")
EUROPEAN_NUMBER = re.compile(r"[+-]?(?:[0-9]+|[0-9]{1,3}(?:\.[0-9]{3})+)(?:,[0-9]+)?")


def flatten_headers(
    header_rows: list[list[str | None]],
    spans: list[list[tuple[float, float] | None]],
    column_spans: list[tuple[float, float]],
) -> list[str]:
    """Flatten marked levels using horizontal (x0, x1) spans, producing unique column names.

    Rows and spans have one position per column. A covered position has text and span None;
    an empty real cell has text "" and its own span. column_spans supplies each column's
    horizontal extent, including positions without a box in the header row (S01-D-006).
    """
    levels: list[list[str]] = [[] for _ in column_spans]
    for row, boxes in zip(header_rows, spans):
        left_text = ""
        left_span = None
        for index, (cell, box) in enumerate(zip(row, boxes)):
            if cell is not None:
                left_text = " ".join(cell.split())
                left_span = box
                part = left_text
            else:
                start, end = column_spans[index]
                covered = left_span is not None and left_span[0] <= start and left_span[1] >= end
                part = left_text if covered else ""
            if part and (not levels[index] or levels[index][-1] != part):
                levels[index].append(part)

    names: list[str] = []
    used: set[str] = set()
    for index, parts in enumerate(levels, start=1):
        base = " / ".join(parts) or f"Column {index}"
        name = base
        suffix = 2
        while name in used:
            name = f"{base} ({suffix})"
            suffix += 1
        used.add(name)
        names.append(name)
    return names


def _is_missing(cell: str | None) -> bool:
    """Recognize only empty cells and the missing markers in FR-115."""
    return cell is None or cell.strip() in MISSING_VALUES


def _number_text(cell: str) -> tuple[str, list[str]]:
    """Remove specified decorations, keeping their hints in first-seen order."""
    hints: list[str] = []
    for match in DECORATION.finditer(cell):
        symbol = match.group()
        hint = "percent" if symbol == "%" else f"currency: {symbol}"
        if hint not in hints:
            hints.append(hint)
    text = DECORATION.sub("", cell).strip().replace("−", "-")
    text = FOOTNOTE.sub("", text).strip()
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1].strip()
    return text, hints


def _uses_comma_decimal(text: str) -> bool:
    """A rightmost comma after a dot, or a non-three-digit comma fraction, settles the style.

    A comma followed by three digits alone is ambiguous (1,234); the default is English.
    Dot-only values never settle European style (VC-120).
    """
    if "," not in text:
        return False
    if "." in text:
        return text.rfind(",") > text.rfind(".")
    fraction = text.rsplit(",", 1)[1]
    return fraction.isascii() and fraction.isdigit() and len(fraction) != 3


def _parse_number(text: str, european: bool) -> Decimal | None:
    """Parse the selected style strictly; malformed separators or leading-zero codes fail."""
    pattern = EUROPEAN_NUMBER if european else ENGLISH_NUMBER
    if pattern.fullmatch(text) is None:
        return None
    grouping, decimal = (".", ",") if european else (",", ".")
    normalized = text.replace(grouping, "").replace(decimal, ".")
    whole = normalized.lstrip("+-").split(".", 1)[0]
    if len(whole) > 1 and whole.startswith("0"):
        return None
    return Decimal(normalized)


def clean_column(values: list[str | None]) -> tuple[pd.Series, list[str]]:
    """Return a typed column and distinct percent/currency hints (S01-D-006).

    Select one decimal style across the whole column before parsing. Every non-missing cell
    must parse, otherwise all original values (including missing markers) remain unchanged
    in an object Series and hints are empty. Numeric columns use int64 for whole values with
    no gaps, float64 otherwise; a whole column outside int64 range stays text (S01-D-007).
    Percent values keep their written scale (FR-115–118).
    """
    texts: list[str | None] = []
    hints: list[str] = []
    for cell in values:
        if _is_missing(cell):
            texts.append(None)
            continue
        text, cell_hints = _number_text(cell)
        texts.append(text)
        for hint in cell_hints:
            if hint not in hints:
                hints.append(hint)

    european = any(_uses_comma_decimal(text) for text in texts if text is not None)
    numbers: list[Decimal | None] = []
    for text in texts:
        if text is None:
            numbers.append(None)
            continue
        number = _parse_number(text, european)
        if number is None:
            return pd.Series(values, dtype=object), []
        numbers.append(number)

    # Decimal prevents a whole value above 2**53 from rounding before int64 conversion.
    if all(number is not None and number == int(number) for number in numbers):
        integers = [int(number) for number in numbers]
        if any(number < INT64_MIN or number > INT64_MAX for number in integers):
            return pd.Series(values, dtype=object), []
        return pd.Series(integers, dtype="int64"), hints
    return pd.Series(
        [float(number) if number is not None else float("nan") for number in numbers],
        dtype="float64",
    ), hints


def build_dataframe(
    names: list[str], rows: list[list[str | None]]
) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    """Build a frame from unique names and rectangular rows, with hints keyed by column name."""
    frame = pd.DataFrame(rows, columns=names, dtype=object)
    hints: dict[str, list[str]] = {}
    for name in names:
        frame[name], hints[name] = clean_column(frame[name].tolist())
    return frame, hints


def row_headers(frame: pd.DataFrame) -> list[str]:
    """Return non-missing labels from the first column only, keeping the column in place (FR-114)."""
    if frame.shape[1] == 0 or is_numeric_dtype(frame.iloc[:, 0].dtype):
        return []
    return [cell for cell in frame.iloc[:, 0].tolist() if not _is_missing(cell)]
