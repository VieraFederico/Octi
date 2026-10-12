"""The Chat view: empty state, message history and the composer (spec FR-020 … FR-024).

The conversation lives in `st.session_state`, so each browser session has its own and it disappears
when the tab is closed (BR-008). PDFs and questions have durable ingestion and Analysis messages.

The composer bar holds the composer and, over its right end, the chat-model picker (D-037). The
choice is kept in `st.session_state[MODEL_PICKER]`; agents use Settings.LLM_MODEL (D-091).
"""

from typing import Any, TypedDict

import streamlit as st

from ui.logo import LOGO_DIR, load_frames, logo_html
from ui.ingestion import BUSY_HINT, is_busy, render_run_message
from ui.upload import PENDING
from ui.analysis import ACTIVE as ACTIVE_ANALYSIS, is_busy as analysis_busy, new_message, queue_analysis, render_analysis_message

MESSAGES = "messages"  # session-state key of the conversation
MODEL_PICKER = "model-picker"  # session-state key of the chosen chat model (also its CSS class hook)
PICKER_WIDTH_PX = 170  # selectboxes take pixels or "stretch", not "content"; fits long model ids

GREETING = "Hi, I'm Octi"
HINT = "Attach a PDF with **+**, or ask a question about your tables."
COMPOSER_PLACEHOLDER = "Ask about your tables…"
QUESTION_PLACEHOLDER = ""  # compatibility with ingestion/upload; chat queues the real Analysis reply


class Message(TypedDict):
    role: str  # "user" or "assistant"
    content: str


def render_chat(model_choices: list[str]) -> None:
    """Empty conversation → centered logo, greeting and inline composer; otherwise history + pinned composer.

    `model_choices` are the chat models offered in the picker; the first one is the default.
    """
    messages: list[Message] = st.session_state.setdefault(MESSAGES, [])
    if messages:
        # Draw the disabled composer before the blocking graph call can start streaming.
        with st.bottom:
            submission = _composer_bar(model_choices)
        for message in messages:
            with st.chat_message(message["role"]):
                if message.get("kind") == "ingestion":
                    render_run_message(message)
                elif message.get("kind") == "analysis":
                    render_analysis_message(message)
                else:
                    st.markdown(message["content"])
                    for name in message.get("file_names", []):
                        st.text(f"Attached {name}")
    else:
        # Centered by `assets/styles.css`. Inside a container, the composer stays inline (FR-020, D-028).
        with st.container(key="empty-state"):
            st.html(logo_html(load_frames(LOGO_DIR)), width="content")  # st.html keeps the monospace art intact
            st.html(f'<h1 class="octi-greeting">{GREETING}</h1>')
            submission = _composer_bar(model_choices)
            with st.container(key="empty-hint"):
                st.markdown(HINT)

    if submission:
        text, uploads = submission_parts(submission)
        if uploads:
            st.session_state[PENDING] = {**uploads[0], "text": text}
        else:
            replies = reply_to(text, [])
            messages.extend(replies)
            st.session_state[ACTIVE_ANALYSIS] = replies[-1]
        st.rerun()  # draw the new state: history instead of the empty state


def chosen_model(model_choices: list[str]) -> str:
    """The chat model picked in the composer, or the default (the first choice) before any pick."""
    return st.session_state.get(MODEL_PICKER) or model_choices[0]


def submission_parts(submission: Any) -> tuple[str, list[dict[str, Any]]]:
    """Read an attachment into memory; the composer accepts one PDF (FR-101)."""
    return submission.text or "", [{"name": uploaded.name, "pdf": uploaded.getvalue()} for uploaded in submission.files]


def reply_to(text: str, file_names: list[str]) -> list[Message]:
    """A user question followed by a queued Analysis message; PDFs use the pending-upload seam."""
    user_parts = ([text] if text else []) + [f"Attached `{name}`" for name in file_names]
    return [
        {"role": "user", "content": "\n\n".join(user_parts)},
        new_message(text),
    ]


def queue_finished_upload_question(state) -> None:
    """Handoff after any finished upload, before sidebar controls render; never repeat a turn."""
    messages = state.get(MESSAGES, [])
    if state.get(ACTIVE_ANALYSIS) not in messages:
        state.pop(ACTIVE_ANALYSIS, None)
    if is_busy(state) or analysis_busy(state) or state.get(PENDING) or state.get("upload-confirming"):
        return
    # Spec 01 still imports its placeholder seam. Suppress that legacy output without editing it.
    for message in messages:
        if message.get("kind") == "ingestion" and message.get("status") == "finished":
            message["text"] = ""
    messages[:] = [message for message in messages if message.get("role") != "assistant"
                   or message.get("kind") or message.get("content", "").strip()]
    for index in range(len(messages) - 1, -1, -1):
        user = messages[index]
        if user.get("role") != "user":
            continue
        if user.get("file_names") and user.get("content", "").strip() and not any(
            message.get("kind") == "analysis" for message in messages[index + 1:]
        ):
            queue_analysis(state, user["content"])
            state["view"] = "Chat"
        break


def _composer_bar(model_choices: list[str]) -> Any:
    """The composer with the model picker laid over its right end by `assets/styles.css`."""
    with st.container(key="composer-bar"):
        # accept_file + file_type: the "+" button only accepts PDFs (FR-024).
        busy = is_busy(st.session_state) or analysis_busy(st.session_state)
        submission = st.chat_input(BUSY_HINT if busy else COMPOSER_PLACEHOLDER, accept_file=True,
                                   file_type=["pdf"], key="composer", disabled=busy)
        # filter_mode=None: a plain dropdown; without it Streamlit lets the user type into the picker (D-045).
        st.selectbox(
            "Chat model", model_choices, key=MODEL_PICKER, label_visibility="collapsed", width=PICKER_WIDTH_PX,
            filter_mode=None,
            disabled=busy,
        )
    return submission
