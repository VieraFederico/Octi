"""Session catalog smoke tests under staged verification (D-118)."""

from ui.catalog import CATALOG, LOADED, ensure_catalog, update_catalog, documents
from tests.stubs import catalog_entry
from services.errors import VectorStoreUnreachableError


def test_catalog_load_and_run_update(make_settings):
    """VC-152 smoke: new results update the library without another read."""
    # Given
    state, calls = {}, []
    old = catalog_entry(document_sha="old")
    def load(settings):
        calls.append(settings)
        return [old]
    # When
    ensure_catalog(state, make_settings(), loader=load)
    new = catalog_entry(table_id="new", document_sha="new")
    update_catalog(state, [new], previous_removed=True)
    ensure_catalog(state, make_settings(), loader=load)
    # Then
    assert state[LOADED] and state[CATALOG] == [new]
    assert len(calls) == 1 and documents(state)[0][0] == "report.pdf"


def test_failed_catalog_load_can_be_retried(make_settings):
    """VC-172/173 smoke: an unavailable library can recover before an upload."""
    # Given
    state = {}
    def fail(settings):
        raise VectorStoreUnreachableError("private backend detail")
    # When
    assert not ensure_catalog(state, make_settings(), loader=fail)
    ensure_catalog(state, make_settings(), loader=lambda _: [], retry=True)
    # Then
    assert state[LOADED] and state[CATALOG] == []
