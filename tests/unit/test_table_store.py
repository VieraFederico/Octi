"""The Parquet Table store: one file per Table, dtypes preserved (spec 01 FR-138, D-047)."""

from pathlib import Path

import pandas as pd
import pytest

from services.errors import TableStoreError
from services.table_store import delete_tables, read_table, write_table
from tests.stubs import extracted_table

TABLE_ID = "b70e6c0d788efb0a-p3-t2"


@pytest.fixture
def frame() -> pd.DataFrame:
    """A cleaned frame with every dtype extraction can produce, including gaps."""
    table = extracted_table(
        ["Region", "Units", "Revenue", "Growth"],
        [["North", "1", "$1,200", "5.5%"], ["South", "2", "n/a", "-2%"], [None, "3", "$900", "1%"]],
    )
    assert table.frame is not None
    return table.frame


def test_a_table_written_is_read_back_equal_with_its_dtypes(table_store_dir: Path, frame: pd.DataFrame) -> None:
    """VC-140 (data part): `read_table` returns the DataFrame that was written, dtypes included."""
    # Given a frame with int64, float64 (with a gap) and text (with a gap) columns
    assert [str(d) for d in frame.dtypes][1:3] == ["int64", "float64"]
    # When it is written and read back
    write_table(TABLE_ID, frame)
    back = read_table(TABLE_ID)
    # Then it is identical, dtypes and missing values included
    pd.testing.assert_frame_equal(back, frame)


def test_the_file_is_named_after_the_table_id(table_store_dir: Path, frame: pd.DataFrame) -> None:
    """SPEC §7 "Table store": `data/tables/<table_id>.parquet`, and nothing else is left behind."""
    write_table(TABLE_ID, frame)
    assert [path.name for path in table_store_dir.iterdir()] == [f"{TABLE_ID}.parquet"]


def test_writing_the_same_table_twice_overwrites_it(table_store_dir: Path, frame: pd.DataFrame) -> None:
    """BR-104: the same id means the same file, not a second one."""
    write_table(TABLE_ID, frame)
    write_table(TABLE_ID, frame.head(1))
    assert len(list(table_store_dir.iterdir())) == 1
    assert len(read_table(TABLE_ID)) == 1


def test_reading_a_table_that_is_not_there_says_so(table_store_dir: Path) -> None:
    """A missing file is a Table store error with a plain sentence (no path)."""
    with pytest.raises(TableStoreError) as caught:
        read_table(TABLE_ID)
    assert str(table_store_dir) not in caught.value.user_message
    assert isinstance(caught.value.__cause__, FileNotFoundError)


def test_delete_removes_files_and_ignores_missing_ones(table_store_dir: Path, frame: pd.DataFrame) -> None:
    """BR-108: deleting by id removes the file; an id with no file is not an error."""
    write_table(TABLE_ID, frame)
    write_table("0000000000000000-p1-t1", frame)
    delete_tables([TABLE_ID, "ffffffffffffffff-p9-t9"])
    assert [path.name for path in table_store_dir.iterdir()] == ["0000000000000000-p1-t1.parquet"]


def test_delete_with_no_store_folder_does_nothing(table_store_dir: Path) -> None:
    assert not table_store_dir.exists()
    delete_tables([TABLE_ID])


def test_a_disk_that_cannot_be_written_raises_a_table_store_error(
    table_store_dir: Path, frame: pd.DataFrame
) -> None:
    """FR-139: a disk failure becomes a `TableStoreError`, the OS error chained."""
    # Given the store folder is really a file, so nothing can be created inside it
    table_store_dir.write_text("not a folder", encoding="utf-8")
    # When a Table is written
    with pytest.raises(TableStoreError) as caught:
        write_table(TABLE_ID, frame)
    # Then the error is ours, the original is kept as the cause, and the message shows no path
    assert caught.value.__cause__ is not None
    assert str(table_store_dir) not in caught.value.user_message


@pytest.mark.parametrize("bad_id", ["../outside", "a/b", "a\\b", "..", ""])
def test_ids_that_could_leave_the_store_folder_are_refused(table_store_dir: Path, frame: pd.DataFrame, bad_id: str) -> None:
    """An id is a file name: anything with a path separator is refused (the Analyst passes ids around)."""
    with pytest.raises(TableStoreError):
        write_table(bad_id, frame)
    with pytest.raises(TableStoreError):
        read_table(bad_id)
    with pytest.raises(TableStoreError):
        delete_tables([bad_id])
