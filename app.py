"""Octi's Streamlit app. Run from the repository root:  streamlit run app.py

Streamlit runs this file top to bottom on every interaction. The expensive start-up check is cached
(`ui/startup.py`); everything else just draws the current session state.
"""

import streamlit as st

from ui.chat import render_chat
from ui.catalog import ensure_catalog
from ui.error_screen import render_error_screen
from ui.icons import OCTOPUS_ICON
from ui.library import render_library
from ui.new_chat import render_new_chat_dialog
from ui.sidebar import LIBRARY, current_view, render_sidebar
from ui.startup import load_startup
from ui.style import apply_style
from ui.upload import process_pending_upload, render_upload_dialog

st.set_page_config(page_title="Octi", page_icon=str(OCTOPUS_ICON))  # an SVG, no emojis (D-036)

apply_style()
startup = load_startup()
if not startup.ok:
    render_error_screen(startup)  # Octi explains what failed and what to do (FR-027, FR-028)
    st.stop()

ensure_catalog(st.session_state, startup.settings)
process_pending_upload(st.session_state)
render_sidebar(startup.settings)
render_new_chat_dialog()  # the "New chat" confirmation, while one is pending
render_upload_dialog()
if current_view() == LIBRARY:  # the sidebar's Chat / Library items set the view
    render_library()
else:
    render_chat(startup.settings.chat_model_choices)
