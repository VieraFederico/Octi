"""Fake keys and stand-in objects (stubs) for the offline tests. A plain module: tests import from it.

Each stub imitates only the part of a real client that Octi uses, and records what was asked of
it, so tests can check both the answer and the calls (for example "nothing was created").
"""

import subprocess
from collections.abc import Callable, Iterator
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import httpx2  # the HTTP library openai 3.x uses; needed only to build fake openai errors
import openai
from pinecone import NotFoundError

from services.health import Clients
from services.settings import Settings
from services.vector_store import IndexStatus

# Unique, searchable fake secrets (>= 8 characters, like real keys): tests assert they never leak.
FAKE_LITELLM_KEY = "sk-FAKE-LITELLM-12345"
FAKE_PINECONE_KEY = "pc-FAKE-PINECONE-12345"
FAKE_LANGSMITH_KEY = "ls-FAKE-LANGSMITH-12345"

MODEL_IDS = ["fake-chat-model", "fake-embedding-model", "another-model"]


# --- Pinecone ----------------------------------------------------------------------------------

OK_INDEX = IndexStatus("ok", 1536, "cosine", 1536, "cosine")
MISSING_INDEX = IndexStatus(
    "missing", 1536, "cosine", reason="The Pinecone index 'octi-tables' does not exist. Create it with: python -m scripts.setup_index"
)


class StubPineconeClient:
    """Stands in for `pinecone.Pinecone`.

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
            raise NotFoundError()  # the real SDK's exception, so the code path is the real one
        dimension, metric = self.index
        return SimpleNamespace(name=name, dimension=dimension, metric=metric)

    def create_index(self, *, name: str, dimension: int, metric: str, spec: object, timeout: int) -> None:
        self.calls.append("create_index")
        self.create_kwargs = {"name": name, "dimension": dimension, "metric": metric, "spec": spec, "timeout": timeout}
        self.index = (dimension, metric)

    # Octi never calls these; they exist so that a call would be recorded and caught by a test.
    def delete_index(self, *_args: object, **_kwargs: object) -> None:
        self.calls.append("delete_index")

    def configure_index(self, *_args: object, **_kwargs: object) -> None:
        self.calls.append("configure_index")

    @property
    def write_calls(self) -> list[str]:
        """Every call that would create, delete or change an index."""
        return [call for call in self.calls if call != "describe_index"]


# --- LiteLLM (openai client) ---------------------------------------------------------------------


def openai_status_error(error_class: type[openai.APIStatusError], status: int, message: str = "error") -> Exception:
    """An openai HTTP error (e.g. `openai.AuthenticationError`, 401) built without any network."""
    request = httpx2.Request("POST", "https://proxy.example.test/v1/chat/completions")
    return error_class(message, response=httpx2.Response(status, request=request), body=None)


def openai_connection_error() -> Exception:
    """The error the openai client raises when the proxy cannot be reached."""
    return openai.APIConnectionError(request=httpx2.Request("POST", "https://proxy.example.test/v1/chat/completions"))


class StubChatModel:
    """Answers `invoke` with a fixed message, or raises `error`. Records each prompt."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.prompts: list[str] = []

    def invoke(self, prompt: str) -> SimpleNamespace:
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(content="OK")


class StubEmbeddings:
    """Answers `embed_query` with a vector of `dimension` zeros, or raises `error`. Records each text."""

    def __init__(self, dimension: int = 1536, error: Exception | None = None) -> None:
        self.dimension = dimension
        self.error = error
        self.texts: list[str] = []

    def embed_query(self, text: str) -> list[float]:
        self.texts.append(text)
        if self.error is not None:
            raise self.error
        return [0.0] * self.dimension


# --- LangSmith ---------------------------------------------------------------------------------


class StubLangSmithClient:
    """Answers `list_projects` with one project, or raises `error`."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    def list_projects(self, limit: int | None = None) -> Iterator[SimpleNamespace]:
        if self.error is not None:
            raise self.error
        return iter([SimpleNamespace(name="octi")])


# --- git ---------------------------------------------------------------------------------------


def git_answer(returncode: int, stderr: str = "") -> Callable[[list[str]], subprocess.CompletedProcess[str]]:
    """A stand-in for running git that always answers with `returncode` and `stderr`."""

    def run(args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, returncode, stdout="", stderr=stderr)

    return run


GIT_NOT_TRACKED = git_answer(1, "error: pathspec did not match any file(s) known to git")
GIT_TRACKED = git_answer(0)
GIT_NOT_A_REPOSITORY = git_answer(128, "fatal: not a git repository (or any of the parent directories): .git")


# --- Client factories for the service check ------------------------------------------------------


def always(stub: Any) -> Callable[[Settings], Any]:
    """A client factory that always returns `stub`."""
    return lambda _settings: stub


def failing(error: Exception) -> Callable[[Settings], Any]:
    """A client factory that cannot even build its client."""

    def build(_settings: Settings) -> Any:
        raise error

    return build


def healthy_clients(**overrides: Any) -> Clients:
    """Client factories where every service answers correctly; pass a field to replace one."""
    healthy = Clients(
        list_models=lambda _settings: MODEL_IDS,
        chat_model=always(StubChatModel()),
        embeddings=always(StubEmbeddings(1536)),
        pinecone=always(StubPineconeClient(index=(1536, "cosine"))),
        langsmith=always(StubLangSmithClient()),
        run_git=GIT_NOT_TRACKED,
    )
    return replace(healthy, **overrides)
