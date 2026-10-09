"""The Pinecone index: a read-only check for the app, and creation for the setup script.

Two entry points with different powers (BR-004, D-010):
- `check_index` only *reads*. The app runs it at start-up and turns the result into a status
  (`ok` / `missing` / `mismatch` / `unreachable`); it never raises for service problems.
- `ensure_index` may *create* the index. Only `scripts/setup_index.py` calls it.

Pinecone exceptions never leave this module raw: they become leaf errors from `services.errors`
with the original exception chained as `__cause__` (FR-008). Both functions accept a `client` so
tests can pass a stub instead of a real `pinecone.Pinecone`.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
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

Outcome = Literal["ok", "missing", "mismatch", "unreachable"]
Shape = tuple[int, str]  # (dimension, metric)


class IndexClient(Protocol):
    """The part of `pinecone.Pinecone` this module uses (the test stub implements the same)."""

    def describe_index(self, name: str) -> Any: ...

    def create_index(self, *, name: str, dimension: int, metric: str, spec: Any, timeout: int) -> Any: ...


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
