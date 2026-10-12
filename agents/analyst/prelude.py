"""The trusted prelude Octi writes at the top of every sandbox `main.py` (SPEC §7, D-090).

The prelude loads the Selected tables into `tables["<alias>"]` (generated code never sees a file
path) and defines `emit(parts)`, the only output channel: it applies FR-226's safety net and prints
exactly one JSON line `{"parts": [...]}` as the last line of stdout. This module only builds text;
the text runs inside the sandbox container (offline tests exec it in-process, BR-204 exception).
"""

import re
import textwrap
import unicodedata
from collections.abc import Mapping, Sequence

from agents.ingestion.schemas import CatalogEntry

WORK_DIR = "/work"  # the read-only mount point inside the container (FR-217)
MAX_ALIAS_LENGTH = 30
EMPTY_VALUE_REASON = "the computed value is empty (missing data in the table)"  # FR-226, verbatim

# `emit` as it will appear in `main.py`. Modules are default arguments so generated code can reuse
# the names `json`, `np`, `pd` and `math` (S02-D-007). The reason literal is filled from the constant.
_EMIT_SOURCE = textwrap.dedent(
    '''\
    def emit(parts, json=json, np=np, pd=pd, math=math):
        """Apply the empty-value safety net and print one JSON line of parts."""

        def python_scalar(value):
            if isinstance(value, np.generic):
                return value.item()
            return value

        def is_empty_value(value):
            # bool is a subclass of int, so it is rejected before the number check (S02-D-007).
            if isinstance(value, bool) or value is None or value is pd.NA or value is pd.NaT:
                return True
            if isinstance(value, float):
                return math.isnan(value) or math.isinf(value)
            return not isinstance(value, (int, str))

        empty_reason = __EMPTY_VALUE_REASON__
        cleaned = []
        for part in parts:
            if not isinstance(part, dict):
                cleaned.append(part)
                continue
            number = python_scalar(part.get("part"))
            status = part.get("status")
            missing = part.get("missing", "")
            raw_values = part.get("values") or {}
            values = {label: python_scalar(value) for label, value in raw_values.items()}
            if status == "answered" and any(is_empty_value(value) for value in values.values()):
                cleaned.append(
                    {"part": number, "status": "missing", "values": {}, "missing": empty_reason}
                )
            elif status != "answered":
                cleaned.append({"part": number, "status": status, "values": {}, "missing": missing})
            else:
                cleaned.append(
                    {"part": number, "status": "answered", "values": values, "missing": missing}
                )
        print(json.dumps({"parts": cleaned}, allow_nan=False), flush=True)
    '''
).replace("__EMPTY_VALUE_REASON__", repr(EMPTY_VALUE_REASON))


def _limit(slug: str) -> str:
    """Cut to `MAX_ALIAS_LENGTH` at a word boundary inside the limit, else hard-cut (S02-D-006)."""
    if len(slug) <= MAX_ALIAS_LENGTH:
        return slug
    window = slug[:MAX_ALIAS_LENGTH]
    if slug[MAX_ALIAS_LENGTH] == "_":
        return window
    boundary = window.rfind("_")
    if boundary == -1:
        return window
    return window[:boundary]


def _alias_base(name: str) -> str:
    """One table name, before the `_2` / `_3` suffix that makes aliases unique."""
    folded = unicodedata.normalize("NFKD", name)
    without_accents = "".join(char for char in folded if not unicodedata.combining(char))
    lowered = without_accents.lower()
    slug = _limit(re.sub(r"[^a-z0-9]+", "_", lowered).strip("_"))
    if not slug:
        return "table"
    if slug[0].isdigit():
        return "t_" + slug
    return slug


def make_aliases(tables: Sequence[CatalogEntry]) -> dict[str, str]:
    """Alias → `table_id` for the Selected tables, in the given order.

    Aliases are short, unique snake_case names derived from the Table names (S02-D-006).
    """
    aliases: dict[str, str] = {}
    used: set[str] = set()
    for entry in tables:
        base = _alias_base(entry.name)
        alias = base
        suffix = 2
        # Repeats are `_2`, `_3`, … A suffix another name already produced is skipped.
        while alias in used:
            alias = f"{base}_{suffix}"
            suffix += 1
        used.add(alias)
        aliases[alias] = entry.table_id
    return aliases


def _tables_block(aliases_to_ids: Mapping[str, str]) -> str:
    """`tables = {alias: pd.read_parquet("/work/<table_id>.parquet"), …}` with `repr` literals."""
    entries = []
    for alias, table_id in aliases_to_ids.items():
        path = f"{WORK_DIR}/{table_id}.parquet"
        entries.append(f"    {alias!r}: pd.read_parquet({path!r})")
    if not entries:
        return "tables = {}"
    return "tables = {\n" + ",\n".join(entries) + ",\n}"


def prelude_source(aliases_to_ids: Mapping[str, str]) -> str:
    """The prelude's Python source: imports, `tables = {alias: pd.read_parquet("/work/<table_id>.parquet")}`
    and `emit(parts)`. The generated code is appended after it."""
    return (
        "import json\n"
        "import math\n"
        "import numpy as np\n"
        "import pandas as pd\n"
        "\n"
        f"{_tables_block(aliases_to_ids)}\n"
        "\n"
        f"{_EMIT_SOURCE}"
    )
