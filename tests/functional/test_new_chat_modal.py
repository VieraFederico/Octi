"""The "New chat" confirmation modal, driven by Streamlit's AppTest (spec FR-025 … FR-025c, D-030)."""

from ui.new_chat import BODY, DONT_WARN_LABEL


def chat_with_two_messages(start_app):
    at = start_app()
    at.chat_input[0].set_value("hello").run()
    assert len(at.chat_message) == 2
    return at


def click_new_chat(at):
    return at.sidebar.button(key="nav-new").click().run()


def modal_is_open(at) -> bool:
    return any(BODY in element.value for element in at.markdown)


def test_new_chat_with_messages_asks_and_cancel_keeps_them(start_app) -> None:
    """VC-030: "New chat" → modal with the warning, Erase, Cancel and the checkbox; Cancel → two messages remain."""
    at = click_new_chat(chat_with_two_messages(start_app))
    assert not at.exception
    assert modal_is_open(at)
    assert at.button(key="new-chat-erase").label == "Erase"
    assert at.button(key="new-chat-cancel").label == "Cancel"
    assert at.checkbox(key="new-chat-dont-warn").label == DONT_WARN_LABEL

    at.button(key="new-chat-cancel").click().run()
    assert not modal_is_open(at)
    assert len(at.chat_message) == 2


def test_erase_empties_the_history_and_brings_back_the_logo(start_app) -> None:
    """VC-030: "New chat" then Erase → history empty, the empty state (logo) is back, modal closed."""
    at = click_new_chat(chat_with_two_messages(start_app))
    at.button(key="new-chat-erase").click().run()
    assert not at.exception
    assert not modal_is_open(at)
    assert len(at.chat_message) == 0
    assert any("octi-logo" in element.value for element in at.main.get("html"))


def test_ticking_dont_warn_then_erase_stops_asking(start_app) -> None:
    """VC-030a: tick the box, Erase; write again; "New chat" → cleared at once, no modal."""
    at = click_new_chat(chat_with_two_messages(start_app))
    at.checkbox(key="new-chat-dont-warn").check().run()
    at.button(key="new-chat-erase").click().run()
    at.chat_input[0].set_value("hello again").run()
    assert len(at.chat_message) == 2

    click_new_chat(at)
    assert not modal_is_open(at)
    assert len(at.chat_message) == 0


def test_ticking_dont_warn_then_cancel_still_asks(start_app) -> None:
    """VC-030b: tick the box, Cancel; "New chat" again → the modal appears, its box unticked."""
    at = click_new_chat(chat_with_two_messages(start_app))
    at.checkbox(key="new-chat-dont-warn").check().run()
    at.button(key="new-chat-cancel").click().run()

    click_new_chat(at)
    assert modal_is_open(at)
    assert at.checkbox(key="new-chat-dont-warn").value is False


def test_empty_conversation_opens_no_modal(start_app) -> None:
    """VC-030c: nothing to erase → no modal."""
    at = click_new_chat(start_app())
    assert not at.exception
    assert not modal_is_open(at)


def test_a_new_session_warns_again(start_app) -> None:
    """VC-030d: warnings turned off in one session; a refresh (a new AppTest session) asks again."""
    first = click_new_chat(chat_with_two_messages(start_app))
    first.checkbox(key="new-chat-dont-warn").check().run()
    first.button(key="new-chat-erase").click().run()

    second = click_new_chat(chat_with_two_messages(start_app))
    assert modal_is_open(second)


def test_new_chat_from_the_library_goes_to_the_chat_view(start_app) -> None:
    """"New chat" always shows the Chat view: from Library with messages, the modal opens over the chat."""
    at = chat_with_two_messages(start_app)
    at.sidebar.button(key="nav-library").click().run()
    click_new_chat(at)
    assert at.session_state["view"] == "Chat"
    assert modal_is_open(at)
