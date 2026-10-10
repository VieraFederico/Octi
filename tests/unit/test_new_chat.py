"""The "New chat" decisions as pure functions over a session-state mapping (spec FR-025 … FR-025c, D-030).

A plain dict stands in for `st.session_state`: the logic does not need Streamlit to be tested.
"""

from ui.chat import MESSAGES
from ui.new_chat import CONFIRMING, WARN, cancel, erase, request_new_chat

TWO_MESSAGES = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "placeholder"}]


def test_messages_and_warnings_on_open_the_modal() -> None:
    """VC-030: with messages and warnings on (the default), "New chat" asks first; nothing is erased yet."""
    state = {MESSAGES: list(TWO_MESSAGES)}
    request_new_chat(state)
    assert state[CONFIRMING] is True
    assert state[MESSAGES] == TWO_MESSAGES


def test_erase_clears_the_conversation_and_closes_the_modal() -> None:
    """VC-030: Erase → empty history, modal closed, warnings still on (the box was not ticked)."""
    state = {MESSAGES: list(TWO_MESSAGES), CONFIRMING: True}
    erase(state, dont_warn_again=False)
    assert state[MESSAGES] == []
    assert state[CONFIRMING] is False
    assert state.get(WARN, True) is True


def test_erase_with_the_box_ticked_turns_warnings_off() -> None:
    """VC-030a: tick "Don't warn me again", Erase → the next "New chat" with messages clears at once."""
    state = {MESSAGES: list(TWO_MESSAGES), CONFIRMING: True}
    erase(state, dont_warn_again=True)
    state[MESSAGES] = list(TWO_MESSAGES)  # the user writes again
    request_new_chat(state)
    assert state[MESSAGES] == []
    assert state[CONFIRMING] is False


def test_cancel_changes_nothing_even_with_the_box_ticked() -> None:
    """VC-030, VC-030b: Cancel keeps the messages and the warnings; the box is ignored, so it asks again."""
    state = {MESSAGES: list(TWO_MESSAGES), CONFIRMING: True}
    cancel(state)
    assert state[MESSAGES] == TWO_MESSAGES
    assert state[CONFIRMING] is False
    request_new_chat(state)
    assert state[CONFIRMING] is True


def test_empty_conversation_opens_no_modal() -> None:
    """VC-030c: nothing to erase → no modal, nothing changes."""
    state = {MESSAGES: []}
    request_new_chat(state)
    assert state.get(CONFIRMING, False) is False
    assert state[MESSAGES] == []


def test_first_click_works_before_the_chat_was_ever_drawn() -> None:
    """A fresh session has no `messages` key yet; "New chat" must not fail on it."""
    state: dict = {}
    request_new_chat(state)
    assert state.get(CONFIRMING, False) is False
