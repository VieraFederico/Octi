"""Fake keys and stand-in objects (stubs) for the offline tests. A plain module: tests import from it.

Each stub imitates only the part of a real client that Octi uses, and records what was asked of
it, so tests can check both the answer and the calls (for example "nothing was created").
"""

import hashlib
import subprocess
from collections.abc import Callable, Iterator
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import httpx2  # the HTTP library openai 3.x uses; needed only to build fake openai errors
import openai
from pinecone import NotFoundError, PineconeConnectionError

from agents.ingestion.pdf.cleaning import build_dataframe, row_headers
from agents.ingestion.schemas import ExtractedTable
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
MISMATCH_INDEX = IndexStatus("mismatch", 1536, "cosine", 3072, "dotproduct", reason="The Pinecone index has the wrong shape.")
# A reason that (wrongly) carries a key: the error screen must never echo a reason (VC-033a).
UNREACHABLE_INDEX = IndexStatus("unreachable", 1536, "cosine", reason=f"connection refused for key {FAKE_PINECONE_KEY}")


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
        self.opened_hosts: list[str] = []
        self.opened_index: object = None

    def describe_index(self, name: str) -> SimpleNamespace:
        self.calls.append("describe_index")
        if self.error is not None:
            raise self.error
        if self.index is None:
            raise NotFoundError()  # the real SDK's exception, so the code path is the real one
        dimension, metric = self.index
        return SimpleNamespace(name=name, dimension=dimension, metric=metric, host="stub-host.example.test")

    def Index(self, name: str = "", host: str = "", **_kwargs: object) -> object:  # noqa: N802 (the SDK's name)
        """Hand out `opened_index` for `host`; not counted in `calls` (it is not a Pinecone request)."""
        self.opened_hosts.append(host)
        return self.opened_index

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


# --- Ingestion: Tables as extraction leaves them --------------------------------------------------


def extracted_table(
    columns: list[str],
    rows: list[list[str | None]],
    *,
    table_id: str = "0123456789abcdef-p1-t1",
    pages: tuple[int, ...] = (1,),
) -> ExtractedTable:
    """An `ExtractedTable` built the way extraction builds it: cells through `build_dataframe`."""
    frame, hints = build_dataframe(columns, rows)
    return ExtractedTable(
        table_id=table_id,
        pages=list(pages),
        parts=[(page, (0.0, 0.0, 1.0, 1.0)) for page in pages],
        columns=list(columns),
        frame=frame,
        hints=hints,
        row_headers=row_headers(frame),
    )


# --- Ingestion: embeddings and a Pinecone index that live in memory ----------------------------------


class FakeEmbeddings:
    """Stands in for the embeddings object: `embed_documents` gives each text a vector made from its hash.

    Same text → same vector. `calls` holds the list of texts of each call; `error` is raised by every
    call (an openai error, to imitate the proxy failing); `events` is a shared list that gets "embed".
    """

    def __init__(self, dimension: int = 8, error: Exception | None = None, events: list[str] | None = None) -> None:
        self.dimension = dimension
        self.error = error
        self.events = events
        self.calls: list[list[str]] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        if self.events is not None:
            self.events.append("embed")
        if self.error is not None:
            raise self.error
        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            vectors.append([(digest[i] + 1) / 256 for i in range(self.dimension)])
        return vectors


class FakePineconeIndex:
    """An in-memory Pinecone index with the calls Octi uses, shaped like the SDK's `Index`.

    - `records[namespace][id] = {"values": [...], "metadata": {...}}`.
    - `calls` lists every method called, in order; `events` (optional, shared) gets the mutating ones
      (`upsert`, `delete`) so a test can interleave them with embeddings and file writes.
    - `fail_on="upsert"` makes that method raise `error` (a Pinecone connection error by default);
      `fail_after=1` lets the first call succeed and fails from the second on.
    - `page_size` is how many items `list` and `fetch_by_metadata` return per page, so tests can see
      the code follow pagination.
    """

    def __init__(
        self,
        *,
        fail_on: str | None = None,
        fail_after: int = 0,
        error: Exception | None = None,
        page_size: int = 100,
        events: list[str] | None = None,
    ) -> None:
        self.records: dict[str, dict[str, dict[str, Any]]] = {}
        self.calls: list[str] = []
        self.upsert_batches: list[int] = []
        self.fail_on = fail_on
        self.fail_after = fail_after
        self.error = error if error is not None else PineconeConnectionError("connection refused")
        self.page_size = page_size
        self.events = events

    # --- helpers for tests --------------------------------------------------------------------

    def put(self, namespace: str, record_id: str, metadata: dict[str, Any], values: list[float] | None = None) -> None:
        """Place a record directly (a state left by an earlier run); not a call."""
        self.records.setdefault(namespace, {})[record_id] = {"values": values or [0.5], "metadata": dict(metadata)}

    def ids(self, namespace: str) -> list[str]:
        return sorted(self.records.get(namespace, {}))

    def _enter(self, method: str) -> None:
        self.calls.append(method)
        if self.events is not None and method in ("upsert", "delete"):
            self.events.append(method)
        if method == self.fail_on:
            if self.calls.count(method) > self.fail_after:
                raise self.error

    # --- the SDK's calls ----------------------------------------------------------------------

    def fetch(self, *, ids: list[str], namespace: str = "", timeout: float | None = None) -> SimpleNamespace:
        self._enter("fetch")
        stored = self.records.get(namespace, {})
        vectors = {i: SimpleNamespace(id=i, **stored[i]) for i in ids if i in stored}
        return SimpleNamespace(vectors=vectors, namespace=namespace)

    def fetch_by_metadata(
        self,
        *,
        filter: dict[str, Any],  # noqa: A002 (the SDK's name)
        namespace: str = "",
        limit: int | None = None,
        pagination_token: str | None = None,
        timeout: float | None = None,
    ) -> SimpleNamespace:
        self._enter("fetch_by_metadata")
        matching = sorted(
            i
            for i, record in self.records.get(namespace, {}).items()
            if all(record["metadata"].get(key) == value for key, value in filter.items())
        )
        size = limit or self.page_size
        start = int(pagination_token or 0)
        page = matching[start : start + size]
        more = start + size < len(matching)
        stored = self.records.get(namespace, {})
        return SimpleNamespace(
            vectors={i: SimpleNamespace(id=i, **stored[i]) for i in page},
            pagination=SimpleNamespace(next=str(start + size)) if more else None,
        )

    def upsert(self, *, vectors: list[dict[str, Any]], namespace: str = "", **_kwargs: object) -> None:
        self._enter("upsert")
        self.upsert_batches.append(len(vectors))
        for vector in vectors:
            self.put(namespace, vector["id"], vector["metadata"], vector["values"])

    def delete(self, *, ids: list[str] | None = None, namespace: str = "", **_kwargs: object) -> None:
        self._enter("delete")
        for record_id in ids or []:
            self.records.get(namespace, {}).pop(record_id, None)

    # Defined last on purpose: inside the class body the name `list` would otherwise hide the builtin
    # in the annotations of every method below it.
    def list(self, *, prefix: str | None = None, limit: int | None = None, namespace: str = "", timeout: float | None = None):
        self._enter("list")
        ids = [i for i in self.ids(namespace) if prefix is None or i.startswith(prefix)]
        size = limit or self.page_size
        for start in range(0, len(ids), size):
            yield SimpleNamespace(vectors=[SimpleNamespace(id=i) for i in ids[start : start + size]])
