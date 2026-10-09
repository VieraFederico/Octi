"""Shared test harness.

Two autouse guards make the default (offline) test run safe by construction:
- no test can open a network connection (spec NFR-006);
- no test can load the repository's real `.env` (spec BR-009).
Tests marked `live` skip both guards: they are the only ones allowed to use real services.
"""

import socket
from collections.abc import Callable, Mapping
from pathlib import Path
from types import SimpleNamespace

import pytest
from pinecone import NotFoundError

from services import settings as settings_module
from services.settings import Settings

REAL_ENV_FILE = (Path(__file__).resolve().parent.parent / ".env").resolve()

FAKE_LITELLM_KEY = "sk-FAKE-LITELLM-12345"
FAKE_PINECONE_KEY = "pc-FAKE-PINECONE-12345"
FAKE_LANGSMITH_KEY = "ls-FAKE-LANGSMITH-12345"


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


def env_without(env: Mapping[str, str], *keys: str) -> dict[str, str]:
    """Copy of `env` with `keys` removed."""
    return {key: value for key, value in env.items() if key not in keys}


class StubPineconeClient:
    """Stands in for `pinecone.Pinecone` and records every call made to it.

    `index` is the existing index as `(dimension, metric)`, or `None` when it does not exist.
    `error` is raised by every call, to simulate a connection or authentication failure.
    """

    def __init__(self, index: tuple[int, object] | None = None, error: Exception | None = None) -> None:
        self.index = index
        self.error = error
        self.calls: list[str] = []
        self.create_kwargs: dict[str, object] = {}

    def describe_index(self, name: str) -> SimpleNamespace:
        self.calls.append("describe_index")
        if self.error is not None:
            raise self.error
        if self.index is None:
            raise NotFoundError()
        dimension, metric = self.index
        return SimpleNamespace(name=name, dimension=dimension, metric=metric)

    def create_index(self, *, name: str, dimension: int, metric: str, spec: object, timeout: int) -> None:
        self.calls.append("create_index")
        self.create_kwargs = {"name": name, "dimension": dimension, "metric": metric, "spec": spec, "timeout": timeout}
        self.index = (dimension, metric)

    def delete_index(self, *_args: object, **_kwargs: object) -> None:
        self.calls.append("delete_index")

    def configure_index(self, *_args: object, **_kwargs: object) -> None:
        self.calls.append("configure_index")

    @property
    def write_calls(self) -> list[str]:
        """Every call that would create, delete or change an index."""
        return [call for call in self.calls if call != "describe_index"]
