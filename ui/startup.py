"""What the app checks when it starts: configuration, the index and the calculation sandbox.

Runs once per server process (`st.cache_resource`), not on every rerun, and makes no LiteLLM call
(D-025): the full service check stays in `scripts/check_services.py`. Because the result is cached,
fixing `.env` or creating the index needs an app restart, and the error screen says so.

`Startup` holds facts only; the words shown to the user are built in `ui/error_screen.py`.
"""

from dataclasses import dataclass

import streamlit as st

from services.errors import InvalidSettingsError
from services.logging_setup import configure_logging
from services.sandbox import DockerStatus, check_docker
from services.settings import Settings, get_settings
from services.vector_store import IndexStatus, check_index


@dataclass(frozen=True)
class Startup:
    """Configuration and the two read-only startup checks, or a settings error."""

    settings: Settings | None
    index_status: IndexStatus | None
    settings_error: InvalidSettingsError | None = None
    docker_status: DockerStatus | None = None

    @property
    def ok(self) -> bool:
        """The shell opens when configuration, index and sandbox are ready (D-031, D-094)."""
        return (
            self.settings_error is None and self.settings is not None
            and self.index_status is not None and self.index_status.outcome == "ok"
            and self.docker_status is not None and self.docker_status.outcome == "ok"
        )


@st.cache_resource(show_spinner="Checking the configuration and services…")
def load_startup() -> Startup:
    try:
        settings = get_settings()
    except InvalidSettingsError as exc:
        return Startup(None, None, exc)
    configure_logging(settings)
    return Startup(settings, check_index(settings), docker_status=check_docker())
