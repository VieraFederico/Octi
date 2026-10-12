"""The Table store: one Parquet file per Table, on the local disk (spec 01 FR-138, D-047).

`data/tables/<table_id>.parquet` holds the cleaned DataFrame exactly as extraction produced it:
Parquet keeps column names and dtypes, so the Analyst loads the same DataFrame ingestion saw.
Writing the same `table_id` again overwrites the file, which is what makes re-ingestion idempotent
(BR-104).

Disk problems become `TableStoreError` with the original chained (FR-008). Messages are plain
sentences: no path, no library text (BR-106).
"""

import contextlib
import logging
import os
from collections.abc import Iterable
from pathlib import Path

import pandas as pd
import pyarrow as pa
from pandas.api.types import is_numeric_dtype

from services.errors import TableStoreError

logger = logging.getLogger(__name__)

# What a failing disk or an unreadable Parquet file raises: the OS's errors and pyarrow's own.
_DISK_ERRORS = (OSError, pa.ArrowException)

# Code constant, overridable by tests (the `table_store_dir` fixture replaces it).
TABLE_STORE_DIR = Path(__file__).resolve().parent.parent / "data" / "tables"


def _path(table_id: str) -> Path:
    """The file of a Table. An id is a file name, so one that could leave the folder is refused."""
    if not table_id or table_id in (".", "..") or "/" in table_id or "\\" in table_id:
        raise TableStoreError("That table id is not valid.")
    return TABLE_STORE_DIR / f"{table_id}.parquet"


def write_table(table_id: str, frame: pd.DataFrame) -> None:
    """Save `frame` as the Table's file, replacing any earlier one.

    The data is written to a temporary file and then moved into place, so a crash never leaves a
    half-written file under the real name (BR-105).
    """
    path = _path(table_id)
    temporary = path.with_suffix(".parquet.tmp")
    try:
        TABLE_STORE_DIR.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(temporary, engine="pyarrow", index=False)
        os.replace(temporary, path)
    except _DISK_ERRORS as exc:
        logger.debug("Writing %s failed", path.name, exc_info=True)
        with contextlib.suppress(OSError):  # the cleanup may fail for the same reason as the write
            temporary.unlink(missing_ok=True)
        raise TableStoreError("Couldn't save the table data.") from exc


def read_table(table_id: str) -> pd.DataFrame:
    """Load a Table's DataFrame (the interface the Analyst uses, SPEC §7)."""
    path = _path(table_id)
    try:
        frame = pd.read_parquet(path, engine="pyarrow")
    except _DISK_ERRORS as exc:
        logger.debug("Reading %s failed", path.name, exc_info=True)
        raise TableStoreError("Couldn't read the saved table data.") from exc
    # pandas 3 reads text columns back as its `str` dtype; extraction builds them as `object`
    # (S01-D-019), with `None` for a gap where `str` has NaN. Casting back gives the Analyst exactly
    # the frame ingestion produced.
    for name in frame.columns:
        column = frame[name]
        if not is_numeric_dtype(column.dtype):
            frame[name] = column.astype(object).where(column.notna(), None)
    return frame


def delete_tables(table_ids: Iterable[str]) -> None:
    """Remove the files of these Tables; an id with no file is skipped (deleting twice is fine)."""
    for table_id in table_ids:
        path = _path(table_id)
        try:
            path.unlink(missing_ok=True)
        except _DISK_ERRORS as exc:
            logger.debug("Deleting %s failed", path.name, exc_info=True)
            raise TableStoreError("Couldn't remove the saved table data.") from exc
