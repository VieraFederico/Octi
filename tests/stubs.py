"""Fake keys and stand-in objects (stubs) for the offline tests. A plain module: tests import from it.

Each stub imitates only the part of a real client that Octi uses, and records what was asked of
it, so tests can check both the answer and the calls (for example "nothing was created").
"""

import hashlib
import json
import subprocess
from collections.abc import Callable, Iterator
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import httpx2  # the HTTP library openai 3.x uses; needed only to build fake openai errors
import openai
from langchain_core.messages import AIMessage, BaseMessage
from pinecone import NotFoundError, PineconeConnectionError
from pydantic import ValidationError

from agents.ingestion.pdf.cleaning import build_dataframe, row_headers
from agents.ingestion.schemas import ColumnDescription, ExtractedTable, TableEnrichment
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


# --- Ingestion: a chat model that answers from a script -------------------------------------------


def enrichment_for(table: ExtractedTable, name: str = "Sales by region and year") -> TableEnrichment:
    """An answer for `table` that passes all five checks of `validate`."""
    columns = [
        ColumnDescription(
            name=column,
            description=f"Values of {column}",
            unit="%" if "percent" in table.hints.get(column, []) else "not stated",
        )
        for column in table.columns
    ]
    return TableEnrichment(name=name, description="What the table measures. Values as printed.", columns=columns)


def invalid_enrichment(table: ExtractedTable) -> TableEnrichment:
    """An answer for `table` that fails exactly one check: the placeholder name `Table 1`."""
    return enrichment_for(table, name="Table 1")


class ScriptedChatModel:
    """Stands in for the chat model of `enrich`: `make_chat_model=scripted.build` in `IngestionDeps`.

    `answers` are used in call order, one per `invoke` (one per `enrich` attempt; Tables are enriched
    one after the other, in reading order). Each item is:
    - a `TableEnrichment`: returned as the parsed answer;
    - a `dict`: the raw JSON the model wrote; parsed only if it is a valid `TableEnrichment`, otherwise
      `parsed` is None and `parsing_error` holds the pydantic error (S01-D-015);
    - an `Exception`: raised by `invoke` (e.g. `openai_connection_error()` or `ProxyUnreachableError`).
    Running out of answers fails the test with an `AssertionError`.

    Records: `model_names` (the `LLM_MODEL` of each `build`), `structured` (`(schema, include_raw)` of
    each `with_structured_output`) and `calls` (each message list sent).
    """

    def __init__(self, answers: list[TableEnrichment | dict[str, Any] | Exception]) -> None:
        self.answers = list(answers)
        self.model_names: list[str] = []
        self.structured: list[tuple[type, bool]] = []
        self.calls: list[list[BaseMessage]] = []

    def build(self, settings: Settings) -> "ScriptedChatModel":
        """The `make_chat_model` factory: records the model the settings name."""
        self.model_names.append(settings.LLM_MODEL)
        return self

    def with_structured_output(self, schema: type, *, include_raw: bool = False, **_kwargs: object) -> "ScriptedChatModel":
        self.structured.append((schema, include_raw))
        return self

    def invoke(self, messages: list[BaseMessage], config: object = None, **_kwargs: object) -> dict[str, Any]:
        """Like `with_structured_output(..., include_raw=True).invoke`: `{"raw", "parsed", "parsing_error"}`."""
        self.calls.append(list(messages))
        if len(self.calls) > len(self.answers):
            raise AssertionError(f"ScriptedChatModel has no answer for call {len(self.calls)}")
        answer = self.answers[len(self.calls) - 1]
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, TableEnrichment):
            return {"raw": AIMessage(answer.model_dump_json()), "parsed": answer, "parsing_error": None}
        raw = AIMessage(json.dumps(answer, ensure_ascii=False))
        try:
            return {"raw": raw, "parsed": TableEnrichment.model_validate(answer), "parsing_error": None}
        except ValidationError as exc:
            return {"raw": raw, "parsed": None, "parsing_error": exc}


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


def catalog_entry(**overrides):
    """A small catalog Table for offline UI smoke tests (D-118)."""
    from datetime import datetime, timezone
    from agents.ingestion.schemas import CatalogEntry
    values = dict(table_id="table", name="Regional sales", description="Sales by region in USD.",
                  columns=[dict(name="Revenue", description="Regional revenue", unit="USD", dtype="int64")],
                  row_headers=["North", "South"], source_file="report.pdf", pages=[1], document_sha="hash",
                  ingested_at=datetime(2026, 1, 1, tzinfo=timezone.utc), preview="Revenue\n100\n200",
                  n_rows=2, n_cols=1, row_headers_total=2)
    values.update(overrides)
    return CatalogEntry(**values)


class ScriptedIngestionRunner:
    """One RunResult per start/resume; optional ordered (node, update) steps per call.

    The functions have the production runner signatures; no client or network is created.
    """

    def __init__(self, results, steps=None):
        from agents.ingestion.state import RunStore
        self.results = iter(results)
        self.steps = iter(steps) if steps is not None else None
        self.calls = []
        self.deps = SimpleNamespace(runs=RunStore())

    def _next(self, on_update):
        result = next(self.results)
        steps = next(self.steps) if self.steps is not None else [("load_pdf", {"page_count": 2})]
        for node, update in steps:
            if on_update:
                on_update(node, update)
        if result.status == "paused" and result.thread_id not in self.deps.runs.thread_ids():
            self.deps.runs.open(result.thread_id, b"fixture pdf")
        if result.status == "finished":
            self.deps.runs.close(result.thread_id)
        return result

    def start(self, graph, deps, source_file, pdf, *, thread_id=None, on_update=None):
        self.calls.append(("start", source_file))
        return self._next(on_update)

    def resume(self, graph, deps, thread_id, choice, *, on_update=None):
        self.calls.append(("resume", choice))
        return self._next(on_update)


# Analyst test helpers.
from collections.abc import Sequence
import copy
import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from datetime import UTC, datetime
from typing import Any

from requests import Response, Session
from requests.exceptions import ConnectionError, HTTPError, ReadTimeout

from agents.analyst.schemas import QueryPlan, QuestionPart
from agents.ingestion.schemas import CatalogEntry, ColumnMetadata
from langchain_core.messages import AIMessage
from pydantic import BaseModel, ValidationError
from services.sandbox import RUN_FOLDER_PREFIX, SandboxResult


ColumnSpec = tuple[str, str, str, str]  # (name, unit, dtype, description)

DEFAULT_COLUMNS: tuple[ColumnSpec, ...] = (
    ("Year", "", "int64", "Fiscal year of the figures"),
    ("Revenue (net)", "USD millions", "float64", "Net revenue of the year"),
)
DEFAULT_ROWS: tuple[tuple[str, ...], ...] = (("2021", "1050.2"), ("2022", "1175.4"), ("2023", "1288.7"))


def analyst_catalog_entry(
    *,
    table_id: str = "aaaaaaaaaaaaaaaa-p1-t1",
    name: str = "Income statement by year",
    description: str = "Revenue and income of ACME for 2021 to 2023, in USD millions.",
    columns: Sequence[ColumnSpec | ColumnMetadata] = DEFAULT_COLUMNS,
    row_headers: Sequence[str] = (),
    source_file: str = "acme-annual-report-2023.pdf",
    pages: Sequence[int] = (1,),
    preview: str | None = None,
    n_rows: int = len(DEFAULT_ROWS),
    row_headers_total: int | None = None,
) -> CatalogEntry:
    """A valid `CatalogEntry`; the preview defaults to the column-names line plus `DEFAULT_ROWS`."""
    metadata = [
        column if isinstance(column, ColumnMetadata) else ColumnMetadata(
            name=column[0], unit=column[1], dtype=column[2], description=column[3]
        )
        for column in columns
    ]
    if preview is None:
        header = " | ".join(column.name for column in metadata)
        preview = "\n".join([header, *(" | ".join(row) for row in DEFAULT_ROWS)])
    return CatalogEntry(
        table_id=table_id,
        name=name,
        description=description,
        columns=metadata,
        row_headers=list(row_headers),
        source_file=source_file,
        pages=list(pages),
        document_sha="a" * 64,
        ingested_at=datetime(2026, 10, 11, tzinfo=UTC),
        preview=preview,
        n_rows=n_rows,
        n_cols=len(metadata),
        row_headers_total=len(row_headers) if row_headers_total is None else row_headers_total,
    )


def query_plan(*part_texts: str, search_phrases: Sequence[str] = ("annual revenue by year",)) -> QueryPlan:
    """A `QueryPlan` with one part per text, numbered from 1; the standalone question joins the texts."""
    parts = [
        QuestionPart(number=number, text=text, entities=[], metrics=[], periods=[], operations=[])
        for number, text in enumerate(part_texts, start=1)
    ]
    return QueryPlan(standalone_question=" ".join(part_texts), parts=parts, search_phrases=list(search_phrases))


class FakeContainer:
    """One scripted execution, with lifecycle and wait arguments recorded."""

    def __init__(self, *, exit_code: int, timed_out: bool, stdout: bytes, stderr: bytes) -> None:
        self.exit_code, self.timed_out = exit_code, timed_out
        self.stdout, self.stderr = stdout, stderr
        self.started = self.killed = self.removed = False
        self.wait_timeouts: list[int] = []

    def start(self) -> None:
        self.started = True

    def wait(self, *, timeout: int) -> dict[str, int]:
        self.wait_timeouts.append(timeout)
        if self.timed_out:
            raise ReadTimeout("scripted calculation timeout")
        return {"StatusCode": self.exit_code}

    def kill(self) -> None:
        self.killed = True

    def logs(self, *, stdout: bool, stderr: bool, stream: bool, follow: bool):
        assert stream and not follow and stdout != stderr
        data = self.stdout if stdout else self.stderr
        for start in range(0, len(data), 16 * 1024):
            yield data[start:start + 16 * 1024]

    def remove(self, *, force: bool) -> None:
        assert force
        self.removed = True


class FakeDockerClient:
    """No SDK/daemon: script reachability, image presence, exit, timeout and byte outputs.

    `create_error` may inject a transport failure after startup. There is deliberately no pull
    method: any attempt to download an image fails the offline test.
    """

    def __init__(
        self, *, reachable: bool = True, image_present: bool = True, exit_code: int = 0,
        timed_out: bool = False, stdout: bytes = b"", stderr: bytes = b"",
        create_error: Exception | None = None,
    ) -> None:
        self.reachable, self.image_present = reachable, image_present
        self.create_error = create_error
        self.closed = False
        self.containers = self.images = self
        self.create_calls: list[dict[str, Any]] = []
        self.image_lookups: list[str] = []
        self.container = FakeContainer(exit_code=exit_code, timed_out=timed_out, stdout=stdout, stderr=stderr)

    def ping(self) -> bool:
        if not self.reachable:
            raise ConnectionError("scripted unreachable daemon")
        return True

    def get(self, name: str) -> object:
        self.ping()
        self.image_lookups.append(name)
        if not self.image_present:
            response = Response()
            response.status_code = 404
            raise HTTPError("scripted missing image", response=response)
        return object()

    def create(self, *, image: str, command: list[str], **kwargs: Any) -> FakeContainer:
        self.ping()
        self.create_calls.append({"image": image, "command": command, **kwargs})
        if self.create_error is not None:
            raise self.create_error
        return self.container

    def close(self) -> None:
        self.closed = True


class AnalystChatModel(ScriptedChatModel):
    """Reuse the ingestion model's recording/factory seam, parsing the requested Analyst schema."""

    def invoke(self, messages, config=None, **_kwargs):
        self.calls.append(list(messages))
        if len(self.calls) > len(self.answers):
            raise AssertionError("No scripted Analyst answer remains")
        answer = self.answers[len(self.calls) - 1]
        if isinstance(answer, Exception):
            raise answer
        data = answer.model_dump(mode="json") if isinstance(answer, BaseModel) else answer
        raw = AIMessage(json.dumps(data))
        try:
            parsed = self.structured[-1][0].model_validate(data)
        except ValidationError as exc:
            return {"raw": raw, "parsed": None, "parsing_error": exc}
        return {"raw": raw, "parsed": parsed, "parsing_error": None}


class AnalystEmbeddings(FakeEmbeddings):
    def embed_query(self, phrase):
        return self.embed_documents([phrase])[0]


class AnalystQueryIndex(FakePineconeIndex):
    """Extend the existing in-memory record store with scripted ranked query results."""

    def __init__(self):
        super().__init__()
        self.query_batches = []
        self.query_calls = []

    def query(self, *, vector, namespace, top_k, include_metadata):
        self._enter("query")
        self.query_calls.append({"vector": vector, "namespace": namespace, "top_k": top_k, "include_metadata": include_metadata})
        ranked = self.query_batches.pop(0) if self.query_batches else [(table_id, 0.9) for table_id in self.ids(namespace)]
        matches = [SimpleNamespace(id=table_id, score=score, metadata=dict(self.records[namespace][table_id]["metadata"]))
                   for table_id, score in ranked[:top_k]]
        return SimpleNamespace(matches=matches)


class StubSandboxRunner:
    """Record prepared inputs and return scripted results; never execute a generated script."""

    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def __call__(self, folder, timeout_s):
        folder = Path(folder)
        resolved = folder.resolve()
        if folder.is_symlink() or resolved.parent != folder.parent.resolve() or not resolved.name.startswith(RUN_FOLDER_PREFIX):
            raise AssertionError("The runner requires an owned temporary folder")
        try:
            self.calls.append({"folder": str(folder), "timeout_s": timeout_s,
                               "files": sorted(path.name for path in folder.iterdir()),
                               "script": (folder / "main.py").read_text(encoding="utf-8")})
            if not self.results:
                raise AssertionError("No scripted sandbox result remains")
            result = self.results.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        finally:
            shutil.rmtree(resolved)


def analyst_deps(settings, folder, answers, results, *, entries=None):
    """Complete offline deps, reusing spec 01's fakes without changing its stub module."""
    from agents.analyst.state import AnalystDeps

    entries = [analyst_catalog_entry()] if entries is None else entries
    index = AnalystQueryIndex()
    for entry in entries:
        flat = entry.model_dump(mode="json")
        flat["columns_info"] = json.dumps(flat.pop("columns"))
        index.put(settings.PINECONE_NAMESPACE, entry.table_id, flat)
        (folder / f"{entry.table_id}.parquet").write_bytes(b"offline table copy fixture")
    model = AnalystChatModel(answers)
    runner = StubSandboxRunner(results)
    deps = AnalystDeps(settings=settings, catalog=entries, embeddings=AnalystEmbeddings(), index=index,
        make_chat_model=model.build, load_catalog=lambda *_: entries,
        table_file=lambda table_id: folder / f"{table_id}.parquet", sandbox_runner=runner, sandbox_base_dir=folder)
    return deps, model, runner


class TraceRecordingSession(Session):
    """An SDK transport that records JSON after real masking hooks, with zero network access."""

    def __init__(self):
        super().__init__()
        self.payloads = []

    def request(self, method, url, **kwargs):
        data = kwargs.get("data")
        if data:
            self.payloads.append(copy.deepcopy(json.loads(data)))
        elif kwargs.get("json") is not None:
            self.payloads.append(copy.deepcopy(kwargs["json"]))
        response = Response()
        response.status_code = 200
        response._content = b"{}"
        response.url = url
        return response


def analysis_result(*, status="answered", answer=None):
    """One final graph-state fixture for the three answer layouts and generic outage layout."""
    from agents.analyst.schemas import CodeDraft, PartOutcome, PartSelection, TableSelection
    from agents.analyst.nodes import OUTAGE_MESSAGE

    entry = analyst_catalog_entry()
    plan = query_plan("What is revenue?")
    selection = TableSelection(parts=[PartSelection(part=1, table_ids=[entry.table_id], verdict="answerable", missing="")])
    outcomes = [PartOutcome(part=1, outcome="answered", values={"Revenue": 1288.7})]
    if status == "partial":
        plan = query_plan("What is revenue?", "What is staff count?")
        outcomes.append(PartOutcome(part=2, outcome="missing", reason="Staff count is absent."))
    elif status == "cannot_answer":
        selection = TableSelection(parts=[PartSelection(part=1, table_ids=[entry.table_id], verdict="missing_data", missing="The requested row is absent.")])
        outcomes = [PartOutcome(part=1, outcome="missing", reason="The requested row is absent.")]
    no_code = status in ("cannot_answer", "error")
    code = 'emit([{"part": 1, "status": "answered", "values": {"Revenue": 1288.7}}])'
    result = {"exit_code": 0, "timed_out": False, "stdout": '{"parts": [{"part": 1, "status": "answered", "values": {"Revenue": 1288.7}}]}', "stderr": ""}
    text = answer or ("The requested row is absent." if no_code else "Revenue is 1,288.7 USD millions.")
    return {"question": "What is revenue?", "window": [], "plan": plan, "candidates": [entry], "selection": selection,
        "selection_attempts": 1, "selection_feedback": [], "code_attempts": 0 if no_code else 1,
        "code_draft": None if no_code else CodeDraft(code=code, approach="Read the row."),
        "sandbox_result": None if no_code else result, "last_failure": None,
        "attempts_history": [] if no_code else [{"code": code, "approach": "Read the row.", **result, "failure": None, "feedback": ""}],
        "part_outcomes": outcomes, "answer_status": "cannot_answer" if status == "error" else status,
        "answer": OUTAGE_MESSAGE if status == "error" else text,
        "error": {"kind": "sandbox", "message": OUTAGE_MESSAGE} if status == "error" else None}


class StubAnalysisRunner:
    """UI-only scripted updates/results; no model, index or sandbox is constructed."""

    def __init__(self, results=None):
        self.results = None if results is None else list(results)
        self.calls = []

    def __call__(self, question, window, deps, confirm_tables=False, *, on_update=None, thread_id=None):
        self.calls.append({"question": question, "window": list(window), "thread_id": thread_id,
                           "confirm_tables": confirm_tables})
        if self.results is None:
            from agents.analyst.nodes import NO_TABLES_MESSAGE
            result = analysis_result(status="cannot_answer", answer=NO_TABLES_MESSAGE if not deps.catalog else "I couldn't answer this question.")
            result.update(candidates=[], selection=None)
        else:
            if not self.results:
                raise AssertionError("No scripted Analysis result remains")
            result = copy.deepcopy(self.results.pop(0))
        if on_update:
            for node, keys in [("understand", ["plan"]), ("retrieve", ["candidates"]), ("select", ["selection"]),
                               ("generate_code", ["code_attempts", "code_draft"]), ("execute", ["sandbox_result"]),
                               ("merge_status", ["answer_status", "part_outcomes"]), ("respond", ["answer"])]:
                if node in ("generate_code", "execute") and not result["code_attempts"]:
                    continue
                on_update(node, {key: result.get(key) for key in keys})
        return result
