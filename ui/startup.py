"""What the app checks when it starts: configuration and the Pinecone index.

Runs once per server process (`st.cache_resource`), not on every rerun, and makes no LiteLLM call
(D-025): the full service check stays in `scripts/check_services.py`. Because the result is cached,
fixing `.env` or creating the index needs an app restart, and the messages say so.
"""

from dataclasses import dataclass

import streamlit as st

from services.errors import InvalidSettingsError
from services.logging_setup import configure_logging
from services.settings import Settings, get_settings
from services.vector_store import IndexStatus, check_index


@dataclass(frozen=True)
class Startup:
    """The start-up result. `problem` is empty when the shell can open; otherwise it is safe UI text."""

    settings: Settings | None
    index_status: IndexStatus | None
    problem: str = ""


@st.cache_resource(show_spinner="Checking the configuration and the Pinecone index…")
def load_startup() -> Startup:
    try:
        settings = get_settings()
    except InvalidSettingsError as exc:
        return Startup(None, None, f"{exc.user_message}\n\nFix them in .env (see .env.example), then restart the app.")
    configure_logging(settings)

    status = check_index(settings)
    if status.outcome != "ok":
        return Startup(settings, status, f"{status.reason}\n\nThen restart the app.")
    return Startup(settings, status)
