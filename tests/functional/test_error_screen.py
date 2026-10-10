"""The Octi error screen in the running app, driven by AppTest (spec FR-027, FR-028, D-031)."""

import pytest

from services.errors import InvalidSettingsError
from tests.stubs import FAKE_PINECONE_KEY, MISMATCH_INDEX, MISSING_INDEX, UNREACHABLE_INDEX


def screen_html(at) -> str:
    return " ".join(element.value for element in at.get("html"))


def assert_no_shell(at) -> None:
    """The error screen replaces the shell: no sidebar items, no composer."""
    assert not at.sidebar.button
    assert not at.chat_input


def test_invalid_configuration_shows_octi_and_the_fix(start_app) -> None:
    """VC-032: `LITELLM_API_KEY` missing → Octi plus a bubble naming it, the `.env.example` instruction
    and the README section; no exception; no shell."""
    at = start_app(settings_error=InvalidSettingsError({"LITELLM_API_KEY": "missing"}))
    assert not at.exception
    html = screen_html(at)
    assert "octi-logo" in html and "octi-bubble" in html
    assert "LITELLM_API_KEY" in html
    assert ".env.example" in html
    assert "README › Getting started" in html
    assert_no_shell(at)


@pytest.mark.parametrize(
    ("status", "advice"),
    [
        (MISSING_INDEX, "python -m scripts.setup_index"),
        (MISMATCH_INDEX, "3072 dimensions / dotproduct"),
        (UNREACHABLE_INDEX, "PINECONE_API_KEY"),
    ],
)
def test_index_problems_show_octi_and_what_to_do(start_app, status, advice) -> None:
    """VC-033: `missing` → setup command; `mismatch` → expected vs actual; `unreachable` → network / key
    hint. No shell in any case, and a reason carrying a key never reaches the screen (VC-033a)."""
    at = start_app(index_status=status)
    assert not at.exception
    html = screen_html(at)
    assert advice in html
    assert FAKE_PINECONE_KEY not in html
    assert_no_shell(at)
