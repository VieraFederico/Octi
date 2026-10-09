"""Octi's Streamlit app. Run from the repository root:  streamlit run app.py

Streamlit runs this file top to bottom on every interaction. The expensive start-up check is cached
(`ui/startup.py`); everything else just draws the current session state.
"""

import streamlit as st

from ui.chat import render_chat
from ui.library import render_library
from ui.sidebar import render_sidebar
from ui.startup import load_startup

st.set_page_config(page_title="Octi", page_icon="🐙")

startup = load_startup()
if startup.problem:
    st.error(startup.problem)  # the Octi error screen replaces this in the next iteration (FR-027, FR-028)
    st.stop()

render_sidebar(startup.settings)
view = st.segmented_control(
    "View", ["Chat", "Library"], default="Chat", required=True, label_visibility="collapsed", key="view"
)
if view == "Library":
    render_library()
else:
    render_chat()
