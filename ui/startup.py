"""What the app checks when it starts: configuration and the Pinecone index.

Runs once per server process (`st.cache_resource`), not on every rerun, and makes no LiteLLM call
(D-025): the full service check stays in `scripts/check_services.py`. Because the result is cached,
fixing `.env` or creating the index needs an app restart, and the error screen says so.

`Startup` holds facts only; the words shown to the user are built in `ui/error_screen.py`.
"""

from dataclasses import dataclass

import streamlit as st

from services.errors import InvalidSettingsError
from services.logging_setup import configure_logging
from services.settings import Settings, get_settings
from services.vector_store import IndexStatus, check_index


@dataclass(frozen=True)
class Startup:
    """The start-up result: settings (or why they failed) and the index status (when settings parsed)."""

    settings: Settings | None
    index_status: IndexStatus | None
    settings_error: InvalidSettingsError | None = None

    @property
    def ok(self) -> bool:
        """True when the shell can open: settings parsed and the index is ready (D-031)."""
        return self.settings_error is None and self.index_status is not None and self.index_status.outcome == "ok"


@st.cache_resource(show_spinner="Checking the configuration and the Pinecone index…")
def load_startup() -> Startup:
    try:
        settings = get_settings()
    except InvalidSettingsError as exc:
        return Startup(None, None, exc)
    configure_logging(settings)
    return Startup(settings, check_index(settings))
