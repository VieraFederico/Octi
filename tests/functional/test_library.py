"""Catalog browsing smoke test (D-118)."""

from tests.stubs import catalog_entry


def test_library_groups_cards_and_filters_documents(start_app):
    """VC-153/154 smoke: a document filter shows only the selected document's cards."""
    # Given
    at = start_app()
    at.session_state["catalog"] = [catalog_entry(), catalog_entry(table_id="other", source_file="other.pdf", name="Other sales")]
    # When
    at.sidebar.button(key="nav-library").click().run()
    # Then
    assert not at.exception
    assert set(at.selectbox(key="library-filter").options) == {"All documents", "report.pdf", "other.pdf"}
    # When
    at.selectbox(key="library-filter").set_value("other.pdf").run()
    # Then
    assert not at.exception and [e.label for e in at.expander] == ["Other sales"]
