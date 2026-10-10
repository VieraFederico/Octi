"""The Chat view: empty state, message history and the composer (spec FR-020 … FR-024).

The conversation lives in `st.session_state`, so each browser session has its own and it disappears
when the tab is closed (BR-008). Until the agents exist, every submission gets a placeholder reply.

The composer bar holds the composer and, over its right end, the chat-model picker (D-037). The
choice is kept in `st.session_state[MODEL_PICKER]`; the Analyst agent (spec 02) reads it through
`chosen_model()`.
"""

from typing import Any, TypedDict

import streamlit as st

from ui.logo import LOGO_DIR, load_frames, logo_html

MESSAGES = "messages"  # session-state key of the conversation
MODEL_PICKER = "model-picker"  # session-state key of the chosen chat model (also its CSS class hook)
PICKER_WIDTH_PX = 170  # selectboxes take pixels or "stretch", not "content"; fits long model ids

GREETING = "Hi, I'm Octi"
HINT = "Attach a PDF with **+**, or ask a question about your tables."
COMPOSER_PLACEHOLDER = "Ask about your tables…"
PDF_PLACEHOLDER = "I can't read PDFs yet: the Ingestion agent arrives in spec 01."
QUESTION_PLACEHOLDER = "I can't answer questions yet: the Analyst agent arrives in spec 02."


class Message(TypedDict):
    role: str  # "user" or "assistant"
    content: str


def render_chat(model_choices: list[str]) -> None:
    """Empty conversation → centered logo, greeting and inline composer; otherwise history + pinned composer.

    `model_choices` are the chat models offered in the picker; the first one is the default.
    """
    messages: list[Message] = st.session_state.setdefault(MESSAGES, [])
    if messages:
        for message in messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
        with st.bottom:  # pinned to the bottom of the page (FR-021)
            submission = _composer_bar(model_choices)
    else:
        # Centered by `assets/styles.css`. Inside a container, the composer stays inline (FR-020, D-028).
        with st.container(key="empty-state"):
            st.html(logo_html(load_frames(LOGO_DIR)), width="content")  # st.html keeps the monospace art intact
            st.html(f'<h1 class="octi-greeting">{GREETING}</h1>')
            submission = _composer_bar(model_choices)
            with st.container(key="empty-hint"):
                st.markdown(HINT)

    if submission:
        text, file_names = submission_parts(submission)
        messages.extend(reply_to(text, file_names))
        st.rerun()  # draw the new state: history instead of the empty state


def chosen_model(model_choices: list[str]) -> str:
    """The chat model picked in the composer, or the default (the first choice) before any pick."""
    return st.session_state.get(MODEL_PICKER) or model_choices[0]


def clear_conversation() -> None:
    st.session_state[MESSAGES] = []


def submission_parts(submission: Any) -> tuple[str, list[str]]:
    """The text and the attached file names. File contents are never read, so no PDF is stored (FR-023)."""
    return submission.text or "", [uploaded.name for uploaded in submission.files]


def reply_to(text: str, file_names: list[str]) -> list[Message]:
    """The user's message and the placeholder reply: PDF first, then the question (FR-022, FR-023, FR-023a)."""
    user_parts = ([text] if text else []) + [f"Attached `{name}`" for name in file_names]
    reply_parts = ([PDF_PLACEHOLDER] if file_names else []) + ([QUESTION_PLACEHOLDER] if text else [])
    return [
        {"role": "user", "content": "\n\n".join(user_parts)},
        {"role": "assistant", "content": "\n\n".join(reply_parts)},
    ]


def _composer_bar(model_choices: list[str]) -> Any:
    """The composer with the model picker laid over its right end by `assets/styles.css`."""
    with st.container(key="composer-bar"):
        # accept_file + file_type: the "+" button only accepts PDFs (FR-024).
        submission = st.chat_input(COMPOSER_PLACEHOLDER, accept_file=True, file_type=["pdf"], key="composer")
        st.selectbox("Chat model", model_choices, key=MODEL_PICKER, label_visibility="collapsed", width=PICKER_WIDTH_PX)
    return submission
