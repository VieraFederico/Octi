"""pytest wiring for the Streamlit app tests: a fixture that starts `app.py` with fake services.

The app checks configuration and the index once per process (`st.cache_resource`), so the cache is
cleared before every test; otherwise one test's fake start-up would leak into the next.
"""

from collections.abc import Callable
from types import SimpleNamespace

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from services.errors import InvalidSettingsError
from services.settings import REPO_ROOT, Settings
from services.vector_store import IndexStatus
from tests.stubs import OK_INDEX

APP_FILE = REPO_ROOT / "app.py"
APP_TIMEOUT_SECONDS = 60  # the first run imports LangChain and Pinecone, which is slow on /mnt/c


@pytest.fixture
def start_app(monkeypatch: pytest.MonkeyPatch, make_settings) -> Callable[..., AppTest]:
    """Start the app with fake settings and a fake index status; LiteLLM factories must not be called."""

    def explode(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the app must not create a LiteLLM client at start-up (D-025)")

    monkeypatch.setattr("services.llm.make_chat_model", explode)
    monkeypatch.setattr("services.llm.make_embeddings", explode)
    # Session catalog reads also stay offline; individual UI tests can seed or override them.
    monkeypatch.setattr("ui.catalog.load_catalog", lambda _settings: [])
    # Startup checks use a ready local fake; sandbox failure tests override this factory.
    monkeypatch.setattr("services.sandbox.make_docker_client", lambda: SimpleNamespace(
        ping=lambda: True, images=SimpleNamespace(get=lambda _name: object()), close=lambda: None,
    ))
    # Speed: every AppTest scans all installed packages for custom-component manifests (~3 s per test on
    # /mnt/c, where each file access crosses into Windows). Octi's local component has no package
    # manifest, so the scan finds nothing; skip it. A renamed scanner fails loudly.
    monkeypatch.setattr("streamlit.components.v2.manifest_scanner.scan_component_manifests", lambda **_: [])

    def start(
        settings: Settings | None = None,
        index_status: IndexStatus = OK_INDEX,
        settings_error: InvalidSettingsError | None = None,
    ) -> AppTest:
        def fake_get_settings() -> Settings:
            if settings_error is not None:
                raise settings_error
            return settings if settings is not None else make_settings()

        monkeypatch.setattr("ui.startup.get_settings", fake_get_settings)
        monkeypatch.setattr("ui.startup.check_index", lambda _settings: index_status)
        st.cache_resource.clear()
        return AppTest.from_file(str(APP_FILE), default_timeout=APP_TIMEOUT_SECONDS).run()

    return start
