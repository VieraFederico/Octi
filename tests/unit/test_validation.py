"""The five deterministic checks on an `enrich` answer (spec 01 FR-131, D-063)."""

import pytest

from agents.ingestion.prompts import FEW_SHOT_EXAMPLES
from agents.ingestion.schemas import ColumnDescription, TableEnrichment
from agents.ingestion.validation import validate
from tests.stubs import extracted_table


@pytest.fixture
def table():
    return extracted_table(
        ["Region", "Revenue / 2023", "Growth"],
        [["North", "$1,200", "5.5%"], ["South", "$900", "-2%"]],
    )


def answer(table, *, name="Sales by region", description="Sales per region.", units=None, overrides=None):
    """A valid answer for `table`; tests break one thing at a time."""
    units = units or {"Growth": "%"}
    columns = [ColumnDescription(name=c, description=f"About {c}.", unit=units.get(c, "")) for c in table.columns]
    data = {"name": name, "description": description, "columns": [c.model_dump() for c in columns]}
    data.update(overrides or {})
    return data


def test_a_good_answer_has_no_feedback(table) -> None:
    """FR-131: a valid answer gives an empty list (as a model and as a dict)."""
    data = answer(table)
    assert validate(data, table) == []
    assert validate(TableEnrichment.model_validate(data), table) == []


def test_every_few_shot_answer_passes_validation_against_its_own_table() -> None:
    """The examples teach what a good answer is: they must pass Octi's own checks."""
    for example in FEW_SHOT_EXAMPLES:
        assert validate(example.answer, example.table) == []


def test_description_over_600_characters_is_a_shape_problem(table) -> None:
    """VC-133 (a): a too-long description gets one sentence naming the field and the limit."""
    feedback = validate(answer(table, description="x" * 601), table)
    assert len(feedback) == 1
    assert "description" in feedback[0] and "600" in feedback[0]


def test_unit_over_40_characters_names_the_column_position(table) -> None:
    """Shape: a nested field is named with its position."""
    data = answer(table)
    data["columns"][1]["unit"] = "u" * 41
    feedback = validate(data, table)
    assert len(feedback) == 1
    assert "columns[1].unit" in feedback[0] and "40" in feedback[0]


def test_missing_required_field_is_a_shape_problem(table) -> None:
    """Shape: a dict without `columns` is reported, not raised."""
    feedback = validate({"name": "Sales", "description": "x"}, table)
    assert len(feedback) == 1
    assert "columns" in feedback[0]


def test_missing_unknown_and_repeated_columns_each_get_their_own_sentence(table) -> None:
    """VC-133 (b): a missing column, an unknown `Revenue 2023` and a repeated `Region`, every one named."""
    # Given an answer that repeats Region, renames Revenue / 2023 and drops Growth
    data = answer(table)
    data["columns"] = [
        {"name": "Region", "description": "r", "unit": ""},
        {"name": "Region", "description": "again", "unit": ""},
        {"name": "Revenue 2023", "description": "money", "unit": "USD"},
    ]
    # When it is validated
    feedback = validate(data, table)
    # Then each problem has its own sentence and names the column
    assert len(feedback) == 4
    joined = "\n".join(feedback)
    assert 'Column "Revenue / 2023" is missing' in joined
    assert 'Column "Growth" is missing' in joined
    assert '"Revenue 2023" is not a column' in joined
    assert '"Region" appears 2 times' in joined


def test_same_columns_in_another_order_is_reported(table) -> None:
    """FR-131 check 2: the order must be the table's order."""
    data = answer(table)
    data["columns"] = list(reversed(data["columns"]))
    feedback = validate(data, table)
    assert len(feedback) == 1
    assert "order" in feedback[0]
    assert "Region, Revenue / 2023, Growth" in feedback[0]


def test_empty_name_description_and_column_description(table) -> None:
    """VC-133 (c): empty texts are reported one by one, the column by name."""
    data = answer(table, name="  ", description="")
    data["columns"][2]["description"] = " "
    feedback = validate(data, table)
    assert len(feedback) == 3
    joined = "\n".join(feedback)
    assert "name is empty" in joined
    assert "description is empty" in joined
    assert 'column "Growth"' in joined


@pytest.mark.parametrize("name", ["Table 2", "table", "DATA", "Untitled", " data "])
def test_generic_names_are_rejected(table, name: str) -> None:
    """VC-133 (d): `Table`, `Table N`, `Data`, `Untitled` in any case are placeholders."""
    feedback = validate(answer(table, name=name), table)
    assert len(feedback) == 1
    assert "placeholder" in feedback[0]


@pytest.mark.parametrize("name", ["Table of sales", "Data by region", "Tables 2023"])
def test_names_that_merely_start_with_a_generic_word_are_fine(table, name: str) -> None:
    assert validate(answer(table, name=name), table) == []


def test_percent_column_needs_a_percent_unit(table) -> None:
    """VC-133 (e): a percent column with unit `USD` gets a sentence naming the column and the unit."""
    feedback = validate(answer(table, units={"Growth": "USD"}), table)
    assert len(feedback) == 1
    assert 'Column "Growth"' in feedback[0] and "USD" in feedback[0]


@pytest.mark.parametrize("unit", ["%", "percent", "Percent change", "% of sales"])
def test_percent_units_are_accepted(table, unit: str) -> None:
    assert validate(answer(table, units={"Growth": unit}), table) == []


def test_a_percent_column_the_answer_forgot_is_only_reported_once(table) -> None:
    """The missing column is check 2's sentence; check 5 does not add a second one for it."""
    data = answer(table)
    data["columns"] = data["columns"][:2]
    feedback = validate(data, table)
    assert len(feedback) == 1
    assert "missing" in feedback[0]
