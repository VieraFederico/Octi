"""Table card presentation smoke test (D-118)."""

from ui.table_card import table_card_html
from tests.stubs import catalog_entry


def test_card_has_fields_escaped_text_and_scrolling_preview():
    """VC-149 smoke: card fields remain readable and PDF markup stays text."""
    # Given
    entry = catalog_entry(description="<script>Sales</script>", row_headers=[str(i) for i in range(15)],
                          row_headers_total=15, preview="<b>Region | Revenue</b>")
    # When
    markup = table_card_html(entry)
    # Then
    assert "<script>" not in markup and "&lt;script&gt;" in markup
    assert "and 5 more" in markup and "overflow-x:auto" in markup
    assert "int64" in markup and "USD" in markup and "page 1" in markup
