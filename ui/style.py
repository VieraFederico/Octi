"""Loads Octi's global stylesheet, `assets/styles.css` (spec FR-019a, D-036).

`.streamlit/config.toml` sets the theme (colors, fonts) for Streamlit's own widgets; the stylesheet
does what the theme cannot (layout, nav items, chat bubbles, the logo) using CSS variables for the
palette and explicit classes. See the comment at the top of the CSS file for the selector rules.
"""

import streamlit as st

from services.settings import REPO_ROOT

STYLESHEET = REPO_ROOT / "assets" / "styles.css"


def apply_style() -> None:
    """Inject the sheet. Given a `.css` path, `st.html` wraps it in `<style>` and it takes no space."""
    st.html(STYLESHEET)
