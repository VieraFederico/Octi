"""The Library groups catalog Tables by Document, with a plain dropdown (FR-150/151)."""

import streamlit as st

from ui.catalog import ALL_DOCUMENTS, FILTER, LOADED, LOAD_FAILURE, documents
from ui.table_card import render_table_card

EMPTY_LIBRARY = "No tables are indexed yet. Attach a PDF in the Chat view to add some."


def render_library() -> None:
    if not st.session_state.get(LOADED):
        st.markdown(LOAD_FAILURE)
        return
    grouped = documents(st.session_state)
    if not grouped:
        st.markdown(EMPTY_LIBRARY)
        return
    choices = [ALL_DOCUMENTS, *(name for name, _ in grouped)]
    if st.session_state.get(FILTER) not in choices:
        st.session_state[FILTER] = ALL_DOCUMENTS
    selected = st.selectbox("Document", choices, key=FILTER, filter_mode=None)
    for name, entries in grouped:
        if selected != ALL_DOCUMENTS and selected != name:
            continue
        date = max(entry.ingested_at for entry in entries).strftime("%Y-%m-%d")
        st.text(f"{name} · {len(entries)} {'table' if len(entries) == 1 else 'tables'} · {date}")
        for entry in entries:
            render_table_card(entry)
