"""The Library view: the indexed tables (spec FR-026). Empty until the Ingestion agent exists (spec 01)."""

import streamlit as st

EMPTY_LIBRARY = "No tables are indexed yet. Attach a PDF in the Chat view to add some."


def render_library() -> None:
    st.markdown(EMPTY_LIBRARY)
