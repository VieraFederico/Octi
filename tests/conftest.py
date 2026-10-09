"""pytest wiring for every test: two automatic guards and two fixtures.

Fake objects (stubs, fake keys) live in `tests/fakes.py` and are imported normally; this file only
holds what pytest itself loads and injects.

The two autouse guards make the default (offline) test run safe by construction:
- no test can open a network connection (spec NFR-006);
- no test can load the repository's real `.env` (spec BR-009).
Tests marked `live` skip both guards: they are the only ones allowed to use real services.
"""

import socket
from collections.abc import Callable
from pathlib import Path

import pytest

from services import settings as settings_module
from services.settings import ENV_FILE, Settings
from tests.fakes import FAKE_LANGSMITH_KEY, FAKE_LITELLM_KEY, FAKE_PINECONE_KEY

REAL_ENV_FILE = ENV_FILE.resolve()


def _is_live(request: pytest.FixtureRequest) -> bool:
    return request.node.get_closest_marker("live") is not None


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    """Any outbound socket connection fails the offline test that attempted it."""
    if _is_live(request):
        return

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("Network access attempted during an offline test")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)


@pytest.fixture(autouse=True)
def block_repo_env_file(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    """Loading the real repo-root `.env` fails the test; temporary fixture files are allowed."""
    if _is_live(request):
        return
    real_load_dotenv = settings_module.load_dotenv

    def guarded_load_dotenv(dotenv_path: object = None, *args: object, **kwargs: object) -> bool:
        if dotenv_path is None or Path(str(dotenv_path)).resolve() == REAL_ENV_FILE:
            raise RuntimeError("A test tried to load the repository's real .env")
        return real_load_dotenv(dotenv_path, *args, **kwargs)

    # Patch the name where it is used: settings.py did `from dotenv import load_dotenv`.
    monkeypatch.setattr(settings_module, "load_dotenv", guarded_load_dotenv)
    settings_module.get_settings.cache_clear()


@pytest.fixture
def fake_env() -> dict[str, str]:
    """A complete, valid environment made only of fake values."""
    return {
        "LITELLM_BASE_URL": "https://proxy.example.test",
        "LITELLM_API_KEY": FAKE_LITELLM_KEY,
        "LLM_MODEL": "fake-chat-model",
        "EMBEDDING_MODEL": "fake-embedding-model",
        "LANGSMITH_TRACING": "false",
        "LANGSMITH_API_KEY": FAKE_LANGSMITH_KEY,
        "PINECONE_API_KEY": FAKE_PINECONE_KEY,
    }


@pytest.fixture
def make_settings(fake_env: dict[str, str]) -> Callable[..., Settings]:
    """Build `Settings` from the fake environment, overriding or removing keys per test.

    Pass a key with value `None` to remove it from the environment.
    """

    def build(**overrides: str | None) -> Settings:
        env: dict[str, str] = dict(fake_env)
        for key, value in overrides.items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        return Settings.from_mapping(env)

    return build
