"""Octi's Streamlit app. Run from the repository root:  streamlit run app.py

Streamlit runs this file top to bottom on every interaction. The expensive start-up check is cached
(`ui/startup.py`); everything else just draws the current session state.
"""

import streamlit as st

from ui.chat import render_chat
from ui.icons import OCTOPUS_ICON
from ui.library import render_library
from ui.sidebar import LIBRARY, current_view, render_sidebar
from ui.startup import load_startup
from ui.style import apply_style

st.set_page_config(page_title="Octi", page_icon=str(OCTOPUS_ICON))  # an SVG, no emojis (D-036)

apply_style()
startup = load_startup()
if startup.problem:
    st.error(startup.problem)  # the Octi error screen replaces this in the next iteration (FR-027, FR-028)
    st.stop()

render_sidebar(startup.settings)
if current_view() == LIBRARY:  # the sidebar's Chat / Library items set the view
    render_library()
else:
    render_chat(startup.settings.chat_model_choices)
