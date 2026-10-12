"""The same expandable Table card in run summaries and the Library (FR-146)."""

import html

import streamlit as st

from agents.ingestion.nodes import format_pages
from agents.ingestion.schemas import CatalogEntry


def table_card_html(entry: CatalogEntry) -> str:
    """Escape every catalog field; wide data scrolls inside the preview, not the page."""
    escape = html.escape
    columns = "".join(
        f"<li><strong>{escape(column.name)}</strong>: {escape(column.description)} "
        f"({escape(column.unit + ', ' if column.unit else '')}{escape(column.dtype)})</li>"
        for column in entry.columns
    )
    headers = ", ".join(entry.row_headers[:10])
    more = max(0, entry.row_headers_total - 10)
    if more:
        headers += f"; and {more} more"
    row_headers = f"<p>Row headers: {escape(headers)}</p>" if headers else ""
    return (
        '<div style="min-width:0;overflow-wrap:anywhere">'
        f"<p>{escape(entry.description)}</p><p>{escape(format_pages(entry.pages))}</p>"
        f"<ul>{columns}</ul>{row_headers}"
        '<pre style="max-width:100%;overflow-x:auto;white-space:pre;'
        'font-family:monospace;padding:0.75rem;border-radius:0.5rem;'
        'background:var(--octi-mantle)">'
        f"{escape(entry.preview)}</pre></div>"
    )


def render_table_card(entry: CatalogEntry) -> None:
    with st.expander(entry.name):
        st.html(table_card_html(entry))
