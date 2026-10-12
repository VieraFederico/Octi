"""The test questions (spec 03 FR-301 … FR-303; D-107, D-112): `eval/questions.yaml` loads into its
schema, covers every category once, and every expected value is recomputed from the sample-PDF
constants, so no expected answer is typed by hand without a check (BR-301)."""

from pathlib import Path

import pytest

from eval.scoring import CATEGORIES, load_questions
from scripts.make_sample_pdfs import (
    ACME_INCOME,
    ACME_MARKET_SHARE,
    ACME_MONTHLY,
    ACME_RD,
    ACME_REGIONAL_NET_SALES,
    INFORME_LABOUR,
    INFORME_POPULATION,
)

QUESTIONS_FILE = Path(__file__).resolve().parents[2] / "eval" / "questions.yaml"

# Each expected value, recomputed from the constants the PDFs are drawn from (keyed by question id
# and value name). Percentages are in percent, as `unit: percent` entries are written.
COMPUTED = {
    ("q01", "net_revenue_2023"): ACME_INCOME[2023]["Revenue (net)"],
    ("q02", "net_sales_2022_usd_millions"): sum(
        row["Net sales (USD thousands)"] for month, row in ACME_MONTHLY.items() if month.startswith("2022-")
    )
    / 1000,
    ("q03", "tasa_de_desempleo_cuyo_2023"): INFORME_LABOUR["Cuyo"]["Tasa de desempleo"],
    ("q04", "rd_share_of_net_revenue_2023"): ACME_RD[2023]["R&D expenses"] / ACME_INCOME[2023]["Revenue (net)"] * 100,
    ("q05", "net_sales_per_inhabitant_patagonia_2023_usd"): ACME_REGIONAL_NET_SALES["Patagonia"][2023]
    * 1_000_000
    / (INFORME_POPULATION["Patagonia"][2023] * 1000),
    ("q08", "rd_expenses_2023"): ACME_RD[2023]["R&D expenses"],
    ("q09", "market_share_patagonia_2023"): ACME_MARKET_SHARE["Patagonia"][2023],
}


def test_questions_file_loads_and_covers_every_category():
    """VC-301, VC-302: the YAML loads into the schema, ids `q01` … `q10`, one question per category,
    and `cannot_answer` questions expect no value."""
    # Given / When: the committed questions file is loaded
    questions = load_questions(QUESTIONS_FILE)

    # Then: ten questions, numbered in order, one per category
    assert [q.id for q in questions] == [f"q{n:02d}" for n in range(1, 11)]
    assert sorted(q.category for q in questions) == sorted(CATEGORIES)
    for q in questions:
        assert q.question and q.expected_answer
        if q.expected_status == "cannot_answer":
            assert q.expected_values == []


def test_expected_values_match_the_sample_pdf_constants():
    """VC-303 (BR-301): every expected value is within 1 % of the value computed from the
    sample-PDF constants, and every computed value has its expected entry."""
    # Given: the committed questions
    questions = load_questions(QUESTIONS_FILE)

    # When: each expected value is paired with its recomputed value
    written = {(q.id, v.name): v.value for q in questions for v in q.expected_values}

    # Then: the same entries exist on both sides, and each pair agrees within 1 %
    assert set(written) == set(COMPUTED)
    for key, expected in written.items():
        assert expected == pytest.approx(COMPUTED[key], rel=0.01), key
