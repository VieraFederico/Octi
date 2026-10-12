"""The Analyst's shared test builders produce valid models (spec 02, D-105)."""

from agents.analyst.schemas import QueryPlan
from agents.ingestion.schemas import CatalogEntry
from tests.analyst_stubs import catalog_entry, query_plan


def test_catalog_entry_defaults_are_a_valid_entry() -> None:
    """A default entry is a complete `CatalogEntry` whose preview starts with its column names."""
    entry = catalog_entry()
    assert isinstance(entry, CatalogEntry)
    assert entry.n_cols == len(entry.columns)
    assert entry.row_headers_total == len(entry.row_headers)
    assert entry.preview.splitlines()[0] == " | ".join(column.name for column in entry.columns)


def test_catalog_entry_accepts_columns_as_tuples() -> None:
    """Columns given as (name, unit, dtype, description) become `ColumnMetadata` in order."""
    entry = catalog_entry(columns=[("Region", "", "text", "Region"), ("Sales", "USD millions", "float64", "Sales")])
    assert [column.name for column in entry.columns] == ["Region", "Sales"]
    assert entry.columns[1].unit == "USD millions"


def test_query_plan_numbers_parts_from_one() -> None:
    """`query_plan` builds one part per text, numbered 1, 2, …"""
    plan = query_plan("What was revenue in 2023?", "What was it in 2022?")
    assert isinstance(plan, QueryPlan)
    assert [part.number for part in plan.parts] == [1, 2]
    assert plan.standalone_question == "What was revenue in 2023? What was it in 2022?"
