"""The sidebar's document preview (spec FR-026a, D-040)."""

from ui.documents import DOCUMENTS_SHOWN, TABLES_SHOWN, DocumentPreview, documents_html


def test_no_documents_shows_the_empty_line() -> None:
    """FR-026a: before any ingestion → the "Documents" heading and "No documents yet"."""
    html = documents_html([])
    assert "Documents" in html and "No documents yet" in html


def test_a_pdf_lists_its_first_tables_and_hides_the_rest_behind_view_all() -> None:
    """VC-025b (FR-026a): 5 tables → 3 visible, the other 2 inside a "View all" expander."""
    tables = [f"Table {number}" for number in range(1, 6)]
    html = documents_html([DocumentPreview("report.pdf", tables)])
    visible, _, hidden = html.partition("<details")
    assert all(f"Table {number}" in visible for number in range(1, TABLES_SHOWN + 1))
    assert "Table 4" in hidden and "Table 5" in hidden
    assert "View all" in hidden


def test_a_pdf_with_few_tables_has_no_view_all() -> None:
    """FR-026a: 2 tables → both visible, no expander."""
    html = documents_html([DocumentPreview("sales.pdf", ["A", "B"])])
    assert "<details" not in html


def test_more_pdfs_than_shown_go_behind_show_more() -> None:
    """VC-025b (FR-026a): 7 PDFs → 5 visible, 2 inside "Show more"."""
    documents = [DocumentPreview(f"doc{number}.pdf") for number in range(7)]
    visible, _, hidden = documents_html(documents).partition("<details")
    assert all(f"doc{number}.pdf" in visible for number in range(DOCUMENTS_SHOWN))
    assert "doc5.pdf" in hidden and "doc6.pdf" in hidden and "Show more" in hidden


def test_names_are_escaped() -> None:
    """VC-025b (FR-026a, FR-031 spirit): a file or table name is shown, never run."""
    html = documents_html([DocumentPreview("<script>.pdf", ["a & b"])])
    assert "<script>" not in html
    assert "&lt;script&gt;.pdf" in html and "a &amp; b" in html


def test_document_navigation_preserves_local_expanders():
    """VC-155 smoke: document controls navigate while table expansion stays local."""
    # Given
    documents = [DocumentPreview('<report>.pdf', ['A', 'B', 'C', 'D'])]
    # When
    markup = documents_html(documents, navigable=True, disabled=True)
    # Then
    assert 'data-document="&lt;report&gt;.pdf"' in markup and 'disabled' in markup
    assert '<details' in markup and 'View all' in markup
