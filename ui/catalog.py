"""Session catalog: load once, then use the run's own results (FR-149, D-067)."""

from collections.abc import Callable, MutableMapping, Sequence
from typing import Any

from agents.ingestion.indexing import load_catalog
from agents.ingestion.schemas import CatalogEntry
from services.errors import VectorStoreError
from services.settings import Settings

CATALOG = "catalog"
LOADED = "catalog-loaded"
ATTEMPTED = "catalog-attempted"
SETTINGS = "ingestion-settings"
FILTER = "library-filter"
ALL_DOCUMENTS = "All documents"
LOAD_FAILURE = "Couldn't load the library. Please try again in a moment."


def ensure_catalog(state: MutableMapping[str, Any], settings: Settings, *,
                   loader: Callable | None = None, retry: bool = False) -> bool:
    """Remember a load failure; only an explicit upload retry repeats that read."""
    state[SETTINGS] = settings
    if state.get(LOADED):
        return True
    if state.get(ATTEMPTED) and not retry:
        return False
    state[ATTEMPTED] = True
    try:
        state[CATALOG] = (loader or load_catalog)(settings)
    except VectorStoreError:
        state[LOADED] = False
        state.setdefault(CATALOG, [])
        return False
    state[LOADED] = True
    return True


def update_catalog(state: MutableMapping[str, Any], entries: Sequence[CatalogEntry], *,
                   previous_removed: bool) -> None:
    """Replace a complete version, or keep possible leftovers after a cleanup failure."""
    names = {entry.source_file for entry in entries}
    existing = {entry.table_id: entry for entry in state.get(CATALOG, [])
                if not previous_removed or entry.source_file not in names}
    existing.update({entry.table_id: entry for entry in entries})
    state[CATALOG] = list(existing.values())


def documents(state: MutableMapping[str, Any]) -> list[tuple[str, list[CatalogEntry]]]:
    """Group by file name; order Documents by their most recent Table's timestamp."""
    grouped: dict[str, list[CatalogEntry]] = {}
    for entry in state.get(CATALOG, []):
        grouped.setdefault(entry.source_file, []).append(entry)
    return sorted(grouped.items(), key=lambda item: max(e.ingested_at for e in item[1]), reverse=True)


def by_hash(state: MutableMapping[str, Any], sha: str) -> CatalogEntry | None:
    return next((entry for entry in state.get(CATALOG, []) if entry.document_sha == sha), None)


def by_name(state: MutableMapping[str, Any], name: str) -> list[CatalogEntry]:
    return [entry for entry in state.get(CATALOG, []) if entry.source_file == name]


def open_library(state: MutableMapping[str, Any], name: str) -> None:
    """One navigation seam for the sidebar, the duplicate modal and run summaries."""
    state["view"] = "Library"
    state[FILTER] = name
