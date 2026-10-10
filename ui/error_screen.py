"""The Octi error screen, shown instead of the shell when the app cannot work (spec FR-027 … FR-028,
decisions D-031, D-032).

    ┌─────────────┐     ╭────────────────────────────╮
    │  Octi       │     │ What failed.               │
    │  (error     │ <───┤                            │
    │   frames)   │     │ What to do.                │
    └─────────────┘     │ Read: README › section     │
                        ╰────────────────────────────╯

Below 640 px the bubble moves under Octi (`assets/styles.css`).

Every message is built here from facts: the variable names of the settings error, and the status
fields of the index check. The index `reason` text is never shown, so even a reason that wrongly
carried a key or raw library text could not reach the screen (BR-007, VC-033a).
"""

from pathlib import Path

import streamlit as st

from services.vector_store import SETUP_COMMAND
from ui.bubble import bubble_html
from ui.logo import ERROR_LOGO_DIR, LOGO_DIR, load_frames, logo_html
from ui.startup import Startup

SERVICE_CHECK_COMMAND = "python -m scripts.check_services"

# README sections the bubble points to; a test checks that each one exists in README.md.
CONFIG_SECTION = "Getting started › Configure your secrets"
INDEX_SECTION = "Getting started › Create the Pinecone index"
SERVICES_SECTION = "Getting started › Check every service"


def render_error_screen(startup: Startup) -> None:
    st.html(error_screen_html(error_message(startup), error_frames()))


def error_message(startup: Startup) -> str:
    """What failed, what to do and which README section to read. Lines break where `\\n` is."""
    if startup.settings_error is not None:
        # The error's own `user_message` names the variables and the rule they broke, never a value.
        return _message(
            startup.settings_error.user_message,
            "What to do: fix them in .env (.env.example lists and explains every variable), then restart the app.",
            CONFIG_SECTION,
        )

    settings, status = startup.settings, startup.index_status
    assert settings is not None and status is not None  # settings parsed, so the index was checked
    name = settings.PINECONE_INDEX_NAME
    if status.outcome == "missing":
        return _message(
            f"The Pinecone index '{name}' does not exist yet.",
            f"What to do: create it with\n{SETUP_COMMAND}\nthen restart the app.",
            INDEX_SECTION,
        )
    if status.outcome == "mismatch":
        return _message(
            f"The Pinecone index '{name}' has the wrong shape. Octi expects "
            f"{status.expected_dimension} dimensions / {status.expected_metric}; the index has "
            f"{status.actual_dimension} dimensions / {status.actual_metric}.",
            "What to do: set PINECONE_INDEX_NAME in .env to a new name, or delete this index in the "
            f"Pinecone console. Then run\n{SETUP_COMMAND}\nand restart the app.",
            INDEX_SECTION,
        )
    return _message(  # "unreachable"
        "Octi could not reach Pinecone, or Pinecone rejected the API key.",
        "What to do: check your internet connection and PINECONE_API_KEY in .env. This command shows "
        f"which one fails:\n{SERVICE_CHECK_COMMAND}\nRestart the app once it passes.",
        SERVICES_SECTION,
    )


def error_screen_html(message: str, frames: list[str]) -> str:
    """Octi on the left, the bubble on the right. Pure: tests read the string."""
    return (
        '<div class="octi-error">'
        f'<div class="octi-error-octi">{logo_html(frames)}</div>'
        f"{bubble_html(message)}"
        "</div>"
    )


def error_frames(error_dir: Path = ERROR_LOGO_DIR, main_dir: Path = LOGO_DIR) -> list[str]:
    """The worried frames; without them the main frames; without those, none (the plain title, FR-027c)."""
    return load_frames(error_dir) or load_frames(main_dir)


def _message(what_failed: str, what_to_do: str, readme_section: str) -> str:
    return f"{what_failed}\n\n{what_to_do}\n\nRead: README › {readme_section}"
