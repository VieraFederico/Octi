"""The Pinecone index: a read-only check for the app, creation for the setup script, and records.

Two entry points with different powers (BR-004, D-010):
- `check_index` only *reads*. The app runs it at start-up and turns the result into a status
  (`ok` / `missing` / `mismatch` / `unreachable`); it never raises for service problems.
- `ensure_index` may *create* the index. Only `scripts/setup_index.py` calls it.

Spec 01 adds the record operations an agent needs: `open_index` (a handle to the index) and
`list_records`, `find_versions`, `upsert_records`, `delete_records`. They know nothing about tables
or documents (D-084): a record is a dict with `id`, `values` and `metadata`, and what lives in the
metadata is the caller's business.

Pinecone exceptions never leave this module raw: they become leaf errors from `services.errors`
with the original exception chained as `__cause__` (FR-008). Both functions accept a `client` so
tests can pass a stub instead of a real `pinecone.Pinecone`.
"""

import logging
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from itertools import batched
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pinecone import ForbiddenError, NotFoundError, Pinecone, PineconeError, ServerlessSpec, UnauthorizedError

from services.errors import IndexMismatchError, VectorStoreAuthenticationError, VectorStoreUnreachableError
from services.settings import Settings

logger = logging.getLogger(__name__)

# Code constants, not configuration (spec §7): the free plan only offers this location.
PINECONE_CLOUD = "aws"
PINECONE_REGION = "us-east-1"
PINECONE_METRIC = "cosine"
# How long creation waits for the new index to be ready. Pinecone's default (None) waits forever.
INDEX_READY_TIMEOUT_SECONDS = 120
SETUP_COMMAND = "python -m scripts.setup_index"

_AUTH_MESSAGE = "Pinecone rejected the API key. Check PINECONE_API_KEY in .env."
_UNREACHABLE_MESSAGE = "Could not reach Pinecone, or it did not answer in time. Check your connection and try again."

# Code constants (spec 01 §7).
UPSERT_BATCH_SIZE = 100
FETCH_BATCH_SIZE = 100  # ids per fetch call (they travel in the URL)
DELETE_BATCH_SIZE = 1_000  # Pinecone's limit of ids per delete call

Outcome = Literal["ok", "missing", "mismatch", "unreachable"]
Shape = tuple[int, str]  # (dimension, metric)


class IndexClient(Protocol):
    """The part of `pinecone.Pinecone` this module uses (the test stub implements the same)."""

    def describe_index(self, name: str) -> Any: ...

    def create_index(self, *, name: str, dimension: int, metric: str, spec: Any, timeout: int) -> Any: ...

    def Index(self, name: str = "", host: str = "", **kwargs: Any) -> Any: ...  # noqa: N802 (the SDK's name)


@dataclass(frozen=True)
class IndexStatus:
    """Result of `check_index`. `reason` is safe to show in the UI (no key, no raw library text)."""

    outcome: Outcome
    expected_dimension: int
    expected_metric: str
    actual_dimension: int | None = None
    actual_metric: str | None = None
    reason: str = ""


def make_pinecone_client(settings: Settings) -> Pinecone:
    """A Pinecone client. Building it makes no network call."""
    return Pinecone(api_key=settings.PINECONE_API_KEY.get_secret_value())


def check_index(settings: Settings, client: IndexClient | None = None) -> IndexStatus:
    """Report the index state without changing anything (FR-014, BR-004)."""
    expected = _expected_shape(settings)
    client = client if client is not None else make_pinecone_client(settings)
    try:
        actual = _describe(settings.PINECONE_INDEX_NAME, client)
    except (VectorStoreAuthenticationError, VectorStoreUnreachableError) as exc:
        return IndexStatus("unreachable", *expected, reason=exc.user_message)

    if actual is None:
        reason = f"The Pinecone index '{settings.PINECONE_INDEX_NAME}' does not exist. Create it with: {SETUP_COMMAND}"
        return IndexStatus("missing", *expected, reason=reason)
    if actual != expected:
        reason = IndexMismatchError(expected=expected, actual=actual).user_message
        return IndexStatus("mismatch", *expected, *actual, reason=reason)
    return IndexStatus("ok", *expected, *actual)


def ensure_index(settings: Settings, client: IndexClient | None = None) -> Literal["created", "already exists"]:
    """Create the index if it does not exist; refuse to touch one with the wrong shape (FR-011 … FR-013).

    Raises `IndexMismatchError`, `VectorStoreAuthenticationError` or `VectorStoreUnreachableError`.
    """
    expected = _expected_shape(settings)
    client = client if client is not None else make_pinecone_client(settings)
    actual = _describe(settings.PINECONE_INDEX_NAME, client)

    if actual is None:
        with _translate_pinecone_errors():
            client.create_index(
                name=settings.PINECONE_INDEX_NAME,
                dimension=settings.EMBEDDING_DIMENSION,
                metric=PINECONE_METRIC,
                spec=ServerlessSpec(cloud=PINECONE_CLOUD, region=PINECONE_REGION),
                timeout=INDEX_READY_TIMEOUT_SECONDS,
            )
        return "created"
    if actual != expected:
        raise IndexMismatchError(expected=expected, actual=actual)
    return "already exists"


def _expected_shape(settings: Settings) -> Shape:
    return (settings.EMBEDDING_DIMENSION, PINECONE_METRIC)


def _describe(name: str, client: IndexClient) -> Shape | None:
    """The index's (dimension, metric), or None when it does not exist."""
    with _translate_pinecone_errors():
        try:
            description = client.describe_index(name)
        except NotFoundError:
            return None
    # `dimension` / `metric` are the SDK's shortcuts for an index with a single dense vector field,
    # which is the only kind Octi creates. The metric may come back as the SDK's `Metric` str-enum.
    metric = getattr(description.metric, "value", description.metric)
    return (int(description.dimension), str(metric))


@contextmanager
def _translate_pinecone_errors() -> Iterator[None]:
    """Turn Pinecone exceptions into leaf errors, keeping the original as `__cause__` (FR-008)."""
    try:
        yield
    except (UnauthorizedError, ForbiddenError) as exc:
        logger.debug("Pinecone rejected the credentials", exc_info=True)
        raise VectorStoreAuthenticationError(_AUTH_MESSAGE) from exc
    except PineconeError as exc:
        # Connection errors, timeouts, server errors (5xx), rate limits and any other SDK failure:
        # in every case the index state cannot be known right now.
        logger.debug("Pinecone call failed", exc_info=True)
        raise VectorStoreUnreachableError(_UNREACHABLE_MESSAGE) from exc


# --- Records (spec 01 FR-138, FR-149) ----------------------------------------------------------


def open_index(settings: Settings, client: IndexClient | None = None) -> Any:
    """A handle to the Octi index, for the record functions below.

    Record calls go to the index's own host, which Pinecone reports in `describe_index`. Raises
    `VectorStoreAuthenticationError` or `VectorStoreUnreachableError` (also when the index is gone).
    """
    client = client if client is not None else make_pinecone_client(settings)
    with _translate_pinecone_errors():
        description = client.describe_index(settings.PINECONE_INDEX_NAME)
        return client.Index(host=description.host)


def query_records(index: Any, namespace: str, vector: list[float], top_k: int) -> list[dict[str, Any]]:
    """Read nearest records with metadata; translate SDK failures at the service boundary.

    Scores and record metadata are returned unchanged. Ranking and Table reconstruction belong
    to the consuming agent (D-084); this function knows nothing about the Analyst's cap.
    """
    with _translate_pinecone_errors():
        response = index.query(vector=vector, namespace=namespace, top_k=top_k, include_metadata=True)
    return [{"id": match.id, "score": match.score, "metadata": match.metadata} for match in response.matches]


def list_records(index: Any, namespace: str) -> list[dict[str, Any]]:
    """The metadata of every record in the namespace.

    Pinecone lists only ids, page by page; the metadata is then fetched in batches (FR-149).
    """
    with _translate_pinecone_errors():
        ids = [item.id for page in index.list(namespace=namespace) for item in page.vectors]
        records: list[dict[str, Any]] = []
        for batch in batched(ids, FETCH_BATCH_SIZE):
            fetched = index.fetch(ids=list(batch), namespace=namespace)
            records.extend(dict(vector.metadata or {}) for vector in fetched.vectors.values())
        return records


def find_versions(index: Any, namespace: str, source_file: str) -> list[dict[str, Any]]:
    """The metadata of every record whose `source_file` equals `source_file`, across all pages.

    A lookup by metadata, not a similarity search: no query vector is involved (S01-D-017, A-103).
    """
    with _translate_pinecone_errors():
        records: list[dict[str, Any]] = []
        token: str | None = None
        while True:
            page = index.fetch_by_metadata(
                filter={"source_file": source_file}, namespace=namespace, pagination_token=token
            )
            records.extend(dict(vector.metadata or {}) for vector in page.vectors.values())
            if page.pagination is None or not page.pagination.next:
                return records
            token = page.pagination.next


def upsert_records(index: Any, namespace: str, records: Sequence[dict[str, Any]]) -> None:
    """Write records (`{"id", "values", "metadata"}`) in batches of 100; an existing id is overwritten."""
    with _translate_pinecone_errors():
        for batch in batched(records, UPSERT_BATCH_SIZE):
            index.upsert(vectors=list(batch), namespace=namespace, show_progress=False)


def delete_records(index: Any, namespace: str, ids: Sequence[str]) -> None:
    """Delete records by id; an id that does not exist is ignored by Pinecone."""
    with _translate_pinecone_errors():
        for batch in batched(ids, DELETE_BATCH_SIZE):
            index.delete(ids=list(batch), namespace=namespace)
