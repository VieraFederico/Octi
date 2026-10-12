"""Test builders and fakes for the Analyst agent (spec 02).

They live here, not in `tests/stubs.py`, while spec 01 is still being implemented in parallel; spec
02's final iteration moves them into `tests/stubs.py` (D-105).
"""

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
from tests.stubs import FakeEmbeddings, FakePineconeIndex, ScriptedChatModel

ColumnSpec = tuple[str, str, str, str]  # (name, unit, dtype, description)

DEFAULT_COLUMNS: tuple[ColumnSpec, ...] = (
    ("Year", "", "int64", "Fiscal year of the figures"),
    ("Revenue (net)", "USD millions", "float64", "Net revenue of the year"),
)
DEFAULT_ROWS: tuple[tuple[str, ...], ...] = (("2021", "1050.2"), ("2022", "1175.4"), ("2023", "1288.7"))


def catalog_entry(
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

    entries = [catalog_entry()] if entries is None else entries
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
