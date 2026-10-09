"""The Chat view: empty state, message history and the composer (spec FR-020 … FR-024).

The conversation lives in `st.session_state`, so each browser session has its own and it disappears
when the tab is closed (BR-008). Until the agents exist, every submission gets a placeholder reply.
"""

from typing import Any, TypedDict

import streamlit as st

from ui.logo import LOGO_DIR, load_frames, logo_html

MESSAGES = "messages"  # session-state key of the conversation

GREETING = "### Hi, I'm Octi 🐙\nAttach a PDF with **+**, or ask a question about your tables."
COMPOSER_PLACEHOLDER = "Ask about your tables…"
PDF_PLACEHOLDER = "I can't read PDFs yet: the Ingestion agent arrives in spec 01."
QUESTION_PLACEHOLDER = "I can't answer questions yet: the Analyst agent arrives in spec 02."

# Empty state: logo, greeting and composer stacked in the middle of the page (FR-020, D-028).
EMPTY_STATE_CSS = """
<style>
.st-key-empty-state { min-height: 70vh; justify-content: center; align-items: center; text-align: center; }
.st-key-empty-state [data-testid="stChatInput"] { width: 100%; }
</style>
"""


class Message(TypedDict):
    role: str  # "user" or "assistant"
    content: str


def render_chat() -> None:
    """Empty conversation → centered logo, greeting and inline composer; otherwise history + pinned composer."""
    messages: list[Message] = st.session_state.setdefault(MESSAGES, [])
    if messages:
        for message in messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
        submission = _composer()  # at the top level, Streamlit pins the composer to the bottom (FR-021)
    else:
        st.markdown(EMPTY_STATE_CSS, unsafe_allow_html=True)
        with st.container(key="empty-state"):  # inside a container, the composer stays inline (FR-020)
            st.markdown(logo_html(load_frames(LOGO_DIR)), unsafe_allow_html=True)
            st.markdown(GREETING)
            submission = _composer()

    if submission:
        text, file_names = submission_parts(submission)
        messages.extend(reply_to(text, file_names))
        st.rerun()  # draw the new state: history instead of the empty state


def clear_conversation() -> None:
    st.session_state[MESSAGES] = []


def submission_parts(submission: Any) -> tuple[str, list[str]]:
    """The text and the attached file names. File contents are never read, so no PDF is stored (FR-023)."""
    return submission.text or "", [uploaded.name for uploaded in submission.files]


def reply_to(text: str, file_names: list[str]) -> list[Message]:
    """The user's message and the placeholder reply: PDF first, then the question (FR-022, FR-023, FR-023a)."""
    user_parts = ([text] if text else []) + [f"📎 {name}" for name in file_names]
    reply_parts = ([PDF_PLACEHOLDER] if file_names else []) + ([QUESTION_PLACEHOLDER] if text else [])
    return [
        {"role": "user", "content": "\n\n".join(user_parts)},
        {"role": "assistant", "content": "\n\n".join(reply_parts)},
    ]


def _composer() -> Any:
    # accept_file + file_type: the "+" button only accepts PDFs (FR-024).
    return st.chat_input(COMPOSER_PLACEHOLDER, accept_file=True, file_type=["pdf"], key="composer")
