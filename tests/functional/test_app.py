"""The Streamlit shell, driven by Streamlit's AppTest (spec FR-019 … FR-026, FR-029, BR-008)."""

import tomllib

from services.errors import InvalidSettingsError
from services.settings import REPO_ROOT
from tests.stubs import MISSING_INDEX

# AppTest's top-level containers: the main area and the bottom bar where a pinned composer lives.
MAIN, BOTTOM = 0, 3


def roots_with_composer(at) -> list[int]:
    return [index for index, root in at._tree.children.items() if list(root.get("chat_input"))]


def markdown_texts(at) -> list[str]:
    return [element.value for element in at.main.markdown]


# --- Opening the app -----------------------------------------------------------------------------


def test_sidebar_shows_new_chat_models_and_status(start_app, make_settings) -> None:
    """VC-025: sidebar has "New chat", both model names as captions and three status items; Chat selected."""
    at = start_app(make_settings(LANGSMITH_TRACING="true"))
    assert not at.exception
    assert [button.label for button in at.sidebar.button] == ["New chat"]
    captions = " ".join(caption.value for caption in at.sidebar.caption)
    assert "fake-chat-model" in captions and "fake-embedding-model" in captions
    status = " ".join(element.value for element in at.sidebar.markdown)
    assert "Configuration OK" in status
    assert "octi-tables" in status
    assert "Tracing on" in status
    assert at.button_group[0].value == "Chat"


def test_empty_chat_shows_logo_greeting_and_inline_composer(start_app) -> None:
    """VC-026: empty conversation → logo, then greeting, then the composer inline (not pinned)."""
    at = start_app()
    texts = markdown_texts(at)
    logo = next(index for index, text in enumerate(texts) if "octi-logo" in text)
    greeting = next(index for index, text in enumerate(texts) if "I'm Octi" in text)
    assert logo < greeting
    assert roots_with_composer(at) == [MAIN]


def test_theme_is_catppuccin_mocha() -> None:
    """VC-026a: the theme file sets the Catppuccin Mocha colors."""
    theme = tomllib.loads((REPO_ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))["theme"]
    assert theme["backgroundColor"] == "#1e1e2e"
    assert theme["secondaryBackgroundColor"] == "#181825"
    assert theme["textColor"] == "#cdd6f4"
    assert theme["primaryColor"] == "#cba6f7"


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
    assert not any("octi-logo" in text or "I'm Octi" in text for text in texts)
    assert roots_with_composer(at) == [BOTTOM]
    assert [message.name for message in at.chat_message] == ["user", "assistant"]
    assert texts[0] == "hello"
    assert "spec 02" in texts[1]


def test_new_chat_clears_the_conversation(start_app) -> None:
    """FR-025 (plain clear until the confirmation modal arrives): "New chat" empties the history."""
    at = start_app()
    at.chat_input[0].set_value("hello").run()
    at.sidebar.button[0].click().run()
    assert len(at.chat_message) == 0
    assert roots_with_composer(at) == [MAIN]


def test_library_view_shows_the_empty_state(start_app) -> None:
    """VC-031: selecting Library → a message saying no tables are indexed yet."""
    at = start_app()
    at.button_group[0].set_value("Library").run()
    assert any("No tables are indexed yet" in text for text in markdown_texts(at))
    assert not at.chat_input


def test_tracing_off_shows_a_sidebar_warning(start_app, make_settings) -> None:
    """VC-034: LANGSMITH_TRACING=false → visible warning in the sidebar."""
    at = start_app(make_settings(LANGSMITH_TRACING="false"))
    assert any("not traced" in warning.value for warning in at.sidebar.warning)


def test_two_sessions_do_not_share_the_conversation(start_app) -> None:
    """VC-035: a message in one browser session does not appear in another."""
    first = start_app()
    first.chat_input[0].set_value("hello").run()
    second = start_app()
    assert len(first.chat_message) == 2
    assert len(second.chat_message) == 0


# --- Start-up problems (plain error until the Octi error screen arrives) ---------------------------


def test_invalid_configuration_shows_an_error_instead_of_the_shell(start_app) -> None:
    """FR-027 (interim): invalid configuration → error naming the variable; no sidebar, no composer, no crash."""
    at = start_app(settings_error=InvalidSettingsError({"LITELLM_API_KEY": "missing"}))
    assert not at.exception
    assert "LITELLM_API_KEY" in at.error[0].value
    assert not at.sidebar.button
    assert not at.chat_input


def test_missing_index_shows_the_setup_command(start_app) -> None:
    """FR-028 (interim): index `missing` → error with the setup command; no shell."""
    at = start_app(index_status=MISSING_INDEX)
    assert "python -m scripts.setup_index" in at.error[0].value
    assert not at.chat_input
