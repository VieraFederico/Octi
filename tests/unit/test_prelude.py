"""Alias names and the prelude text, including `emit`'s safety net run in-process (VC-223, BR-204).

The tiny scripts below only call Octi's own `emit`. They are not generated analysis code, which
never runs in this process (BR-204).
"""

import json

import numpy as np
import pandas as pd

from agents.analyst.prelude import (
    EMPTY_VALUE_REASON,
    MAX_ALIAS_LENGTH,
    WORK_DIR,
    make_aliases,
    prelude_source,
)
from agents.analyst.schemas import EmittedPart
from tests.stubs import analyst_catalog_entry as catalog_entry


def test_make_aliases_builds_unique_identifiers_in_order() -> None:
    """VC-223 (alias part, FR-217, S02-D-006): names become unique snake_case identifiers, in order."""
    # Given table names with accents, punctuation, a long phrase, no usable characters, a leading
    # digit, a hard-cut word, duplicates, and a suffix that collides with another name
    tables = [
        catalog_entry(table_id="id-cafe", name="Café Año"),
        catalog_entry(table_id="id-punct", name="Revenue (net) — 2023!"),
        catalog_entry(table_id="id-empty", name="***"),
        catalog_entry(table_id="id-blank", name=""),
        catalog_entry(table_id="id-digit", name="2023 results"),
        catalog_entry(table_id="id-long", name="Alpha Beta Gamma Delta Epsilon Zeta Extra"),
        catalog_entry(table_id="id-hard", name="abcdefghijklmnopqrstuvwxyz0123456789"),
        catalog_entry(table_id="id-rev", name="Revenue"),
        catalog_entry(table_id="id-rev-2", name="Revenue"),
        catalog_entry(table_id="id-foo", name="foo"),
        catalog_entry(table_id="id-foo-2", name="foo 2"),
        catalog_entry(table_id="id-foo-again", name="foo"),
        catalog_entry(table_id="id-ones", name="1" * (MAX_ALIAS_LENGTH + 1)),
    ]

    # When aliases are derived
    aliases = make_aliases(tables)

    # Then each name follows the rule, repeats are _2 / _3, and the dict keeps the given order
    expected = {
        "cafe_ano": "id-cafe",
        "revenue_net_2023": "id-punct",
        "table": "id-empty",
        "table_2": "id-blank",
        "t_2023_results": "id-digit",
        "alpha_beta_gamma_delta_epsilon": "id-long",
        "abcdefghijklmnopqrstuvwxyz0123": "id-hard",
        "revenue": "id-rev",
        "revenue_2": "id-rev-2",
        "foo": "id-foo",
        "foo_2": "id-foo-2",
        "foo_3": "id-foo-again",
        "t_" + ("1" * MAX_ALIAS_LENGTH): "id-ones",
    }
    assert list(aliases) == list(expected)
    assert aliases == expected
    assert all(alias.isidentifier() for alias in aliases)


def test_prelude_source_loads_each_table_and_compiles() -> None:
    """VC-223 (source part, FR-217, S02-D-007): the prelude imports, reads /work/<id>.parquet, and compiles."""
    # Given two aliases in a fixed order
    aliases = {"cafe_ano": "id-cafe", "t_2023_results": "bbbbbbbbbbbbbbbb-p2-t1"}

    # When the prelude source is built
    source = prelude_source(aliases)

    # Then the four imports come first, each alias reads its parquet path via repr(), and it compiles
    assert WORK_DIR == "/work"
    assert source.startswith("import json\nimport math\nimport numpy as np\nimport pandas as pd\n")
    first = f"{'cafe_ano'!r}: pd.read_parquet({f'{WORK_DIR}/id-cafe.parquet'!r})"
    second = f"{'t_2023_results'!r}: pd.read_parquet({f'{WORK_DIR}/bbbbbbbbbbbbbbbb-p2-t1.parquet'!r})"
    assert first in source
    assert second in source
    assert source.index(first) < source.index(second)
    assert "def emit(parts, json=json, np=np, pd=pd, math=math)" in source
    assert "allow_nan=False" in source
    assert "flush=True" in source
    assert EMPTY_VALUE_REASON in source
    compile(source, "<prelude>", "exec")

    # Given no selected tables
    empty = prelude_source({})

    # Then the tables mapping is empty and the source still compiles
    assert "tables = {}" in empty
    compile(empty, "<prelude>", "exec")


def test_emit_safety_net_prints_one_json_line_last(capsys) -> None:
    """VC-223 (FR-226, BR-204): empty answered values become missing; one JSON line is printed last."""
    # Given parts that mix empty values, real numbers and text, a numpy part number, and a missing part
    parts: list[object] = [
        {"part": 1, "status": "answered", "values": {"revenue": float("nan")}},
        {"part": 2, "status": "answered", "values": {"revenue": None}},
        {"part": 3, "status": "answered", "values": {"revenue": float("inf")}},
        {"part": 4, "status": "answered", "values": {"revenue": float("-inf")}},
        {"part": 5, "status": "answered", "values": {"revenue": object()}},
        {"part": 6, "status": "answered", "values": {"revenue": np.float64("nan")}},
        {"part": 7, "status": "answered", "values": {"revenue": pd.NA}},
        {"part": 8, "status": "answered", "values": {"revenue": pd.NaT}},
        {"part": 9, "status": "answered", "values": {"flag": True}},
        {"part": 10, "status": "answered", "values": {"year": 2023}},
        {"part": 11, "status": "answered", "values": {"rate": 1.5}},
        {"part": 12, "status": "answered", "values": {"count": np.int64(7)}},
        {"part": 13, "status": "answered", "values": {"rate": np.float64(1.25)}},
        {"part": 14, "status": "answered", "values": {"name": "café"}},
        {
            "part": 15,
            "status": "missing",
            "missing": "the year 2024 is not in the table",
            "values": {"year": 2024},
        },
        {"part": 16, "status": "answered", "values": {"ok": 1, "bad": None}},
        {"part": np.int64(17), "status": "answered", "values": {"n": np.int64(1)}},
    ]

    # When the prelude runs in-process and a tiny script calls emit after reusing json and np
    lines = _exec_emit(capsys, parts)

    # Then the marker is not JSON, and the only JSON line is the last line of stdout
    assert lines[0] == "rows 1"
    assert len(lines) == 2
    line = lines[-1]
    assert line.isascii()
    assert "\\u00e9" in line
    payload = json.loads(line)
    models = [EmittedPart.model_validate(part) for part in payload["parts"]]
    by_part = {model.part: model for model in models}

    for number in (1, 2, 3, 4, 5, 6, 7, 8, 9, 16):
        assert by_part[number].status == "missing"
        assert by_part[number].missing == EMPTY_VALUE_REASON
        assert by_part[number].values == {}

    assert by_part[10].status == "answered"
    assert by_part[10].values == {"year": 2023}
    assert type(by_part[10].values["year"]) is int
    assert by_part[11].status == "answered"
    assert by_part[11].values == {"rate": 1.5}
    assert type(by_part[11].values["rate"]) is float
    assert by_part[12].status == "answered"
    assert by_part[12].values == {"count": 7}
    assert type(by_part[12].values["count"]) is int
    assert by_part[13].status == "answered"
    assert by_part[13].values == {"rate": 1.25}
    assert type(by_part[13].values["rate"]) is float
    assert by_part[14].status == "answered"
    assert by_part[14].values == {"name": "café"}
    assert by_part[15].status == "missing"
    assert by_part[15].missing == "the year 2024 is not in the table"
    assert by_part[15].values == {}
    assert by_part[17].status == "answered"
    assert by_part[17].values == {"n": 1}
    assert type(payload["parts"][16]["part"]) is int


def test_emit_copies_a_non_dict_part_unchanged(capsys) -> None:
    """VC-223 (S02-D-007): a part that is not a dict is left as it is, for the app to reject."""
    # Given a list whose first part is not a dict
    parts: list[object] = [
        "not-a-dict",
        {"part": 1, "status": "missing", "missing": "no row", "values": {"x": 1}},
    ]

    # When emit runs
    lines = _exec_emit(capsys, parts)

    # Then the non-dict is unchanged and the missing part keeps its reason with no values
    payload = json.loads(lines[-1])
    assert payload["parts"][0] == "not-a-dict"
    missing = EmittedPart.model_validate(payload["parts"][1])
    assert missing.status == "missing"
    assert missing.missing == "no row"
    assert missing.values == {}


def _exec_emit(capsys, parts: list[object]) -> list[str]:
    """Exec the prelude, inject an in-memory table, and call `emit` after clobbering module names."""
    namespace: dict[str, object] = {}
    exec(prelude_source({}), namespace)
    namespace["tables"] = {"income": pd.DataFrame({"Year": [2021]})}
    namespace["parts"] = parts
    script = (
        "print('rows', len(tables['income']))\n"
        "json = None\n"
        "np = None\n"
        "pd = None\n"
        "math = None\n"
        "emit(parts)\n"
    )
    exec(script, namespace)
    return capsys.readouterr().out.splitlines()
