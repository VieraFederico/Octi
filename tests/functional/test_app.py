"""The Streamlit shell, driven by Streamlit's AppTest (spec FR-019 … FR-026, FR-029, BR-008).

The "New chat" modal and the error screen have their own files: `test_new_chat_modal.py`,
`test_error_screen.py`.
"""

import tomllib

from services.settings import REPO_ROOT

# AppTest's top-level containers: the main area and the bottom bar where a pinned composer lives.
MAIN, BOTTOM = 0, 3


def roots_with_composer(at) -> list[int]:
    return [index for index, root in at._tree.children.items() if list(root.get("chat_input"))]


def markdown_texts(at) -> list[str]:
    return [element.value for element in at.main.markdown]


def html_texts(node) -> list[str]:  # node: an AppTest or one of its blocks
    """The bodies of the `st.html` elements under `node`, or the whole app (AppTest has no `html` shortcut)."""
    return [element.value for element in node.get("html")]


def main_elements(at) -> list[str]:
    """The main area's elements in page order, as "<type>:<text>", so tests can check vertical order."""

    def walk(node) -> list[str]:
        children = getattr(node, "children", None)
        if children:
            return [line for child in children.values() for line in walk(child)]
        return [f"{node.type}:{getattr(node, 'value', '')}"]

    return walk(at.main)


def sidebar_button(at, key: str):
    return at.sidebar.button(key=key)


# --- Opening the app -----------------------------------------------------------------------------


def test_sidebar_shows_wordmark_nav_documents_and_status(start_app, make_settings) -> None:
    """VC-025: "Octi" (back to the chat), "New chat" (with shortcut), "Library", the Documents section
    (empty before spec 01) and a status popover with config, index, tracing and the embedding model."""
    at = start_app(make_settings(LANGSMITH_TRACING="true"))
    assert not at.exception
    assert [button.label for button in at.sidebar.button] == ["Octi", "New chat", "Library"]
    assert sidebar_button(at, "nav-new").proto.shortcut
    assert at.session_state["view"] == "Chat"
    assert any("Documents" in text and "No documents yet" in text for text in html_texts(at.sidebar))
    popover = at.sidebar.get("popover")[0]
    assert at.sidebar.get_by_key("status-ok") is not None  # green dot (the label is tested in unit tests)
    status = " ".join(html_texts(popover))
    assert "Configuration OK" in status
    assert "octi-tables" in status
    assert "Tracing on" in status
    assert "fake-embedding-model" in status


def test_wordmark_goes_back_to_the_chat_keeping_the_conversation(start_app) -> None:
    """D-040: Library, then "Octi" → the Chat view again, with the same messages."""
    at = start_app()
    at.chat_input[0].set_value("hello").run()
    sidebar_button(at, "nav-library").click().run()
    sidebar_button(at, "home").click().run()
    assert at.session_state["view"] == "Chat"
    assert len(at.chat_message) == 2


def test_model_picker_offers_the_configured_models(start_app, make_settings) -> None:
    """VC-025a (D-037): the picker lists LLM_MODEL first (the default), then LLM_MODEL_CHOICES; a pick is
    kept in the session and survives the switch from the empty state to the pinned composer."""
    at = start_app(make_settings(LLM_MODEL_CHOICES="model-b, fake-chat-model, model-c"))
    picker = at.selectbox(key="model-picker")
    assert picker.options == ["fake-chat-model", "model-b", "model-c"]
    assert picker.value == "fake-chat-model"
    picker.set_value("model-b").run()
    at.chat_input[0].set_value("hello").run()
    assert at.selectbox(key="model-picker").value == "model-b"
    assert at.session_state["model-picker"] == "model-b"


def test_model_picker_cannot_be_typed_into(start_app) -> None:
    """D-045: the picker is a plain dropdown; typing into it (Streamlit's default filter box) is off."""
    from streamlit.proto.SelectWidgetFilterMode_pb2 import SelectWidgetFilterMode

    picker = start_app().selectbox(key="model-picker")
    assert picker.proto.filter_mode == SelectWidgetFilterMode.FILTER_MODE_NONE
    assert not picker.proto.accept_new_options


def test_empty_chat_shows_logo_greeting_and_inline_composer(start_app) -> None:
    """VC-026: empty conversation → logo, then greeting, then the composer inline (not pinned)."""
    at = start_app()
    elements = main_elements(at)
    logo = next(index for index, text in enumerate(elements) if text.startswith("html:") and "octi-logo" in text)
    greeting = next(index for index, text in enumerate(elements) if "I'm Octi" in text)
    composer = next(index for index, text in enumerate(elements) if text.startswith("chat_input:"))
    assert logo < greeting < composer
    assert roots_with_composer(at) == [MAIN]


def test_theme_is_catppuccin_mocha() -> None:
    """VC-026a: the theme file sets the Catppuccin Mocha colors."""
    theme = tomllib.loads((REPO_ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))["theme"]
    assert theme["backgroundColor"] == "#1e1e2e"
    assert theme["secondaryBackgroundColor"] == "#181825"
    assert theme["textColor"] == "#cdd6f4"
    assert theme["primaryColor"] == "#cdd6f4"
    assert theme["baseRadius"] == theme["buttonRadius"] == "0.75rem"


def test_composer_accepts_only_pdf_files(start_app) -> None:
    """VC-029: the composer's file picker accepts only the pdf type."""
    composer = start_app().chat_input[0]
    assert composer.proto.accept_file
    assert list(composer.proto.file_type) == [".pdf"]


# --- Chatting ------------------------------------------------------------------------------------


def test_first_message_shows_history_and_pins_the_composer(start_app) -> None:
    """VC-027: submit "hello" → logo and greeting gone, composer pinned, user "hello" then the spec-02 placeholder."""
    at = start_app()
    at.chat_input[0].set_value("hello").run()
    assert not at.exception
    texts = markdown_texts(at)
    assert not any("octi-logo" in text or "I'm Octi" in text for text in html_texts(at.main))
    assert roots_with_composer(at) == [BOTTOM]
    assert [message.name for message in at.chat_message] == ["user", "assistant"]
    assert texts[0] == "hello"
    assert "spec 02" in texts[1]


def test_library_view_shows_the_empty_state(start_app) -> None:
    """VC-031: selecting Library → a message saying no tables are indexed yet."""
    at = start_app()
    sidebar_button(at, "nav-library").click().run()
    assert any("No tables are indexed yet" in text for text in markdown_texts(at))
    assert sidebar_button(at, "nav-library").proto.type == "secondary"  # highlighted while open
    assert not at.chat_input


def test_tracing_off_marks_the_status_button_and_explains_in_the_popover(start_app, make_settings) -> None:
    """VC-034 (D-036): LANGSMITH_TRACING=false → the status button reads "Not traced"; its popover says
    runs are not traced and how to turn tracing on."""
    at = start_app(make_settings(LANGSMITH_TRACING="false"))
    popover = at.sidebar.get("popover")[0]
    assert at.sidebar.get_by_key("status-warn") is not None  # peach dot (the label is tested in unit tests)
    assert any("not traced" in text and "LANGSMITH_TRACING=true" in text for text in html_texts(popover))


def test_two_sessions_do_not_share_the_conversation(start_app) -> None:
    """VC-035: a message in one browser session does not appear in another."""
    first = start_app()
    first.chat_input[0].set_value("hello").run()
    second = start_app()
    assert len(first.chat_message) == 2
    assert len(second.chat_message) == 0
