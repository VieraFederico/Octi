"""The "New chat" confirmation (spec FR-025 … FR-025c, decision D-030).

The decisions are pure functions over a session-state mapping (tests pass a plain dict):

    "New chat" clicked ─┬─ no messages ─────────────────────→ nothing happens (FR-025c)
                        ├─ warnings off (this session) ─────→ cleared at once (FR-025b)
                        └─ otherwise ───────────────────────→ modal: Erase / Cancel (FR-025)
    Erase  → cleared; if "Don't warn me again" was ticked, warnings off for this session (FR-025a)
    Cancel → nothing changes; the box is ignored (FR-025a)

"A confirmation is pending" is a session-state flag, `CONFIRMING`, not just "the dialog function was
called once". While it is set, `render_new_chat_dialog` opens the dialog on every full run, so the
modal survives any rerun; Erase, Cancel and dismissing it (X, Esc, click outside) clear it. The
opt-out lives in session state too, so a refresh (a new session) brings the warning back (D-030).
"""

from collections.abc import MutableMapping
from typing import Any

import streamlit as st

from ui.chat import MESSAGES

WARN = "new-chat-warn"  # session-state key: False once the user ticked "Don't warn me again"
CONFIRMING = "new-chat-confirming"  # session-state key: True while the modal is open

TITLE = "Start a new chat?"
BODY = "This erases the current conversation. It can't be undone."
DONT_WARN_LABEL = "Don't warn me again"


def request_new_chat(state: MutableMapping[str, Any]) -> None:
    """What the sidebar's "New chat" button does (see the diagram above)."""
    if not state.get(MESSAGES):
        return
    if state.get(WARN, True):
        state[CONFIRMING] = True
    else:
        state[MESSAGES] = []


def erase(state: MutableMapping[str, Any], dont_warn_again: bool) -> None:
    state[MESSAGES] = []
    state[CONFIRMING] = False
    if dont_warn_again:
        state[WARN] = False


def cancel(state: MutableMapping[str, Any]) -> None:
    state[CONFIRMING] = False


def render_new_chat_dialog() -> None:
    """Call on every run (from `app.py`): opens the modal while a confirmation is pending."""
    if st.session_state.get(CONFIRMING):
        _confirm()


def _dismissed() -> None:
    """X, Esc or a click outside the modal count as Cancel."""
    cancel(st.session_state)


@st.dialog(TITLE, on_dismiss=_dismissed)
def _confirm() -> None:
    st.markdown(BODY)
    # Not stored on tick: only Erase reads it (FR-025a). When the modal closes the checkbox is no longer
    # drawn, so Streamlit forgets it and the next modal starts unticked.
    dont_warn_again = st.checkbox(DONT_WARN_LABEL, key="new-chat-dont-warn")
    with st.container(key="new-chat-actions", horizontal=True, horizontal_alignment="right"):
        # A click inside a dialog reruns only the dialog; st.rerun() redraws the whole app, which also
        # closes the modal because CONFIRMING is now False.
        if st.button("Cancel", key="new-chat-cancel", type="tertiary"):
            cancel(st.session_state)
            st.rerun()
        if st.button("Erase", key="new-chat-erase", type="primary"):  # tinted red by assets/styles.css
            erase(st.session_state, dont_warn_again)
            st.rerun()
