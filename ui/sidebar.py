"""The sidebar: one screen with everything (spec FR-019, FR-026a, FR-029, D-036 … D-040).

From the top:
- "Octi", the wordmark. Clicking it goes back to the current chat (the Chat view).
- "New chat" (shortcut Cmd/Ctrl+Shift+O; Cmd+N belongs to the browser) and "Library".
- "Documents": every ingested PDF with its first tables (`ui/documents.py`).
- At the bottom, "Status: Operational" (or "Status: Not traced"), whose popover opens from the button.

The selected view lives in `st.session_state[VIEW]`; `app.py` reads it to draw the main area.
"""

import html

import streamlit as st

from services.settings import Settings
from ui.documents import render_documents
from ui.ingestion import is_streaming
from ui.analysis import is_busy as analysis_busy
from ui.icons import CHECK, WARNING, img_tag
from ui.new_chat import request_new_chat

VIEW = "view"  # session-state key of the selected view
CHAT, LIBRARY = "Chat", "Library"
NEW_CHAT_SHORTCUT = "Mod+Shift+O"  # Mod = Cmd on macOS, Ctrl elsewhere


def current_view() -> str:
    return st.session_state.setdefault(VIEW, CHAT)


def render_sidebar(settings: Settings) -> None:
    view = current_view()
    disabled = is_streaming(st.session_state) or analysis_busy(st.session_state)
    with st.sidebar:
        # Every `key` below becomes a `st-key-<key>` class that `assets/styles.css` targets.
        st.button("Octi", key="home", on_click=_select, args=(CHAT,), type="tertiary", help="Back to the chat", disabled=disabled)

        with st.container(key="sidebar-nav"):
            st.button(
                "New chat", key="nav-new", icon=":material/add:", on_click=_new_chat, shortcut=NEW_CHAT_SHORTCUT,
                type="tertiary", width="stretch", disabled=disabled,
            )
            st.button(
                LIBRARY, key="nav-library", icon=":material/table_chart:", on_click=_select, args=(LIBRARY,),
                type="secondary" if view == LIBRARY else "tertiary",  # the stylesheet tints "secondary"
                width="stretch", disabled=disabled,
            )

        render_documents(disabled=disabled)

        # The inner container's key picks the status dot's color in `assets/styles.css`.
        with st.container(key="sidebar-footer"), st.container(key="status-ok" if settings.LANGSMITH_TRACING else "status-warn"):
            _status(settings)


def status_label(settings: Settings) -> str:
    """The status button's text: tracing off is the only start-up problem the shell opens with (D-031)."""
    return "Status: Operational" if settings.LANGSMITH_TRACING else "Status: Not traced"


def _status(settings: Settings) -> None:
    """The start-up checks (FR-019) in a popover that opens from the button: config, index, tracing (FR-029)."""
    with st.popover(status_label(settings), key="status-popover", width="stretch"):
        tracing = (
            (CHECK, f"Tracing on (LangSmith project <code>{html.escape(settings.LANGSMITH_PROJECT)}</code>)")
            if settings.LANGSMITH_TRACING
            else (WARNING, "Tracing is off: runs are not traced. Set <code>LANGSMITH_TRACING=true</code> in .env and restart.")
        )
        rows = [
            (CHECK, "Configuration OK"),
            (CHECK, f"Pinecone index <code>{html.escape(settings.PINECONE_INDEX_NAME)}</code> ready"),
            tracing,
        ]
        status = "".join(f'<div class="octi-status-row">{img_tag(icon)}<span>{text}</span></div>' for icon, text in rows)
        # The embedding model is fixed (it sets the index dimension), so it is shown here, not picked.
        note = f'<div class="octi-status-note">Embeddings: <code>{html.escape(settings.EMBEDDING_MODEL)}</code></div>'
        st.html(status + note)


def _select(name: str) -> None:
    st.session_state[VIEW] = name


def _new_chat() -> None:
    st.session_state[VIEW] = CHAT  # a new chat is always shown in the Chat view (the modal opens over it)
    request_new_chat(st.session_state)  # clears, asks first, or does nothing (ui/new_chat.py)
