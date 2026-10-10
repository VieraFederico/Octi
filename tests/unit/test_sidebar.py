"""The sidebar's status button text (spec FR-019, FR-029, D-036)."""

from ui.sidebar import status_label


def test_status_label_says_operational_when_tracing_is_on(make_settings) -> None:
    """VC-025: tracing on → "Status: Operational"."""
    assert status_label(make_settings(LANGSMITH_TRACING="true")) == "Status: Operational"


def test_status_label_says_not_traced_when_tracing_is_off(make_settings) -> None:
    """VC-034: tracing off → "Status: Not traced"."""
    assert status_label(make_settings(LANGSMITH_TRACING="false")) == "Status: Not traced"
