"""Pre-run upload decision smoke tests (D-118)."""

from ui.upload import check_upload
from ui.catalog import CATALOG, LOADED
from agents.ingestion.pdf.tables import document_sha
from tests.stubs import catalog_entry


def test_identical_file_precedes_replacement():
    """VC-102 smoke: identical bytes select the existing document before the name check."""
    # Given
    state = {LOADED: True, CATALOG: [catalog_entry(document_sha=document_sha(b"pdf"))]}
    # When
    decision = check_upload(state, "report.pdf", b"pdf")
    # Then
    assert decision["kind"] == "identical" and decision["document"] == "report.pdf"


def test_same_name_needs_replacement_and_new_name_can_start():
    """VC-103 smoke: a replacement reports its table count; a new name can start."""
    # Given
    state = {LOADED: True, CATALOG: [catalog_entry(document_sha="old")]}
    # When
    replacement = check_upload(state, "report.pdf", b"new")
    fresh = check_upload(state, "new.pdf", b"new")
    # Then
    assert replacement == {"kind": "replace", "document": "report.pdf", "count": 1}
    assert fresh["kind"] == "start"
