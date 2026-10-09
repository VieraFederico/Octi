"""Pinecone index: read-only check and creation (spec FR-008, FR-011 … FR-014, BR-004)."""

import pytest
from pinecone import ForbiddenError, Metric, PineconeConnectionError, PineconeTimeoutError, ServiceError, UnauthorizedError

from services.errors import IndexMismatchError, VectorStoreAuthenticationError, VectorStoreUnreachableError
from services.vector_store import (
    PINECONE_CLOUD,
    PINECONE_METRIC,
    PINECONE_REGION,
    SETUP_COMMAND,
    check_index,
    ensure_index,
    make_pinecone_client,
)
from tests.conftest import FAKE_PINECONE_KEY, StubPineconeClient

# --- check_index (what the app runs: read-only) -------------------------------------------------


def test_check_reports_missing_with_setup_command(make_settings) -> None:
    """VC-018: no index → `missing`, the reason names the setup command; nothing is created."""
    # Given Pinecone has no index
    client = StubPineconeClient(index=None)
    # When the index is checked
    status = check_index(make_settings(), client)
    # Then it reports `missing` with the command to fix it, and changes nothing
    assert status.outcome == "missing"
    assert SETUP_COMMAND in status.reason
    assert client.write_calls == []


def test_check_reports_ok_for_matching_index(make_settings) -> None:
    """VC-018: matching index → `ok`; nothing is changed."""
    # Given an index with 1536 dimensions and cosine
    client = StubPineconeClient(index=(1536, "cosine"))
    # When the index is checked
    status = check_index(make_settings(), client)
    # Then it reports `ok` with expected == actual
    assert status.outcome == "ok"
    assert (status.actual_dimension, status.actual_metric) == (1536, "cosine")
    assert client.write_calls == []


def test_check_accepts_metric_enum_from_pinecone(make_settings) -> None:
    """VC-018: the SDK may return the metric as its `Metric` enum; it still counts as cosine."""
    # Given the index reports `Metric.COSINE`
    client = StubPineconeClient(index=(1536, Metric.COSINE))
    # When the index is checked / Then it is `ok`
    assert check_index(make_settings(), client).outcome == "ok"


@pytest.mark.parametrize("actual", [(3072, "cosine"), (1536, "dotproduct")])
def test_check_reports_mismatch_with_expected_and_actual(make_settings, actual: tuple[int, str]) -> None:
    """VC-018: wrong dimension or metric → `mismatch` with expected vs actual; nothing is changed."""
    # Given an index with the wrong shape
    client = StubPineconeClient(index=actual)
    # When the index is checked
    status = check_index(make_settings(), client)
    # Then it reports `mismatch` with both sides
    assert status.outcome == "mismatch"
    assert (status.expected_dimension, status.expected_metric) == (1536, "cosine")
    assert (status.actual_dimension, status.actual_metric) == actual
    assert f"actual {actual[0]}" in status.reason
    assert client.write_calls == []


@pytest.mark.parametrize(
    "error",
    [
        PineconeConnectionError("connection refused"),
        PineconeTimeoutError("read timed out"),
        ServiceError(),
        UnauthorizedError(f"Invalid API key {FAKE_PINECONE_KEY}"),
        ForbiddenError(),
    ],
)
def test_check_reports_unreachable_with_safe_reason(make_settings, error: Exception) -> None:
    """VC-018a: connection, timeout, server or authentication failure → `unreachable`, safe reason."""
    # Given Pinecone fails (one error message even echoes the key)
    client = StubPineconeClient(error=error)
    # When the index is checked
    status = check_index(make_settings(), client)
    # Then it reports `unreachable` with a reason that has no key material and no raw library text
    assert status.outcome == "unreachable"
    assert status.reason
    assert FAKE_PINECONE_KEY not in status.reason
    assert str(error) not in status.reason
    assert client.write_calls == []


def test_check_tells_auth_failure_apart_from_connection_failure(make_settings) -> None:
    """VC-018a: the safe reason differs for a rejected key and for a network problem."""
    # Given one client that cannot connect and one whose key is rejected
    settings = make_settings()
    network = check_index(settings, StubPineconeClient(error=PineconeConnectionError("down")))
    auth = check_index(settings, StubPineconeClient(error=UnauthorizedError()))
    # Then both are `unreachable`, but the reasons say different things
    assert network.reason != auth.reason
    assert "PINECONE_API_KEY" in auth.reason


# --- ensure_index (what the setup script runs) --------------------------------------------------


def test_ensure_creates_missing_index_with_the_expected_shape(make_settings) -> None:
    """VC-015: no index → create one with dimension 1536, cosine, serverless aws/us-east-1."""
    # Given Pinecone has no index
    client = StubPineconeClient(index=None)
    # When the index is ensured
    result = ensure_index(make_settings(), client)
    # Then exactly one create call is made with the expected shape and location
    assert result == "created"
    assert client.write_calls == ["create_index"]
    kwargs = client.create_kwargs
    assert (kwargs["name"], kwargs["dimension"], kwargs["metric"]) == ("octi-tables", 1536, "cosine")
    assert (kwargs["spec"].cloud, kwargs["spec"].region) == ("aws", "us-east-1")
    assert (PINECONE_CLOUD, PINECONE_REGION, PINECONE_METRIC) == ("aws", "us-east-1", "cosine")


def test_ensure_waits_a_bounded_time_for_the_new_index(make_settings) -> None:
    """VC-015: creation waits for readiness with a finite timeout (never forever)."""
    # Given Pinecone has no index / When the index is ensured
    client = StubPineconeClient(index=None)
    ensure_index(make_settings(), client)
    # Then the readiness wait is a positive number of seconds (None would wait forever)
    timeout = client.create_kwargs["timeout"]
    assert isinstance(timeout, int) and timeout > 0


def test_ensure_leaves_matching_index_alone(make_settings) -> None:
    """VC-016: matching index → no create/delete call."""
    # Given a matching index
    client = StubPineconeClient(index=(1536, "cosine"))
    # When the index is ensured / Then nothing changes
    assert ensure_index(make_settings(), client) == "already exists"
    assert client.write_calls == []


def test_ensure_raises_mismatch_without_changing_anything(make_settings) -> None:
    """VC-012 / VC-017: dimension 3072 → IndexMismatchError (expected 1536 / actual 3072); no writes."""
    # Given an index with 3072 dimensions
    client = StubPineconeClient(index=(3072, "cosine"))
    # When the index is ensured / Then it refuses with both shapes
    with pytest.raises(IndexMismatchError) as caught:
        ensure_index(make_settings(), client)
    assert caught.value.expected == (1536, "cosine")
    assert caught.value.actual == (3072, "cosine")
    assert client.write_calls == []


def test_ensure_chains_connection_error_as_unreachable(make_settings) -> None:
    """VC-012: connection error → VectorStoreUnreachableError with the original as `__cause__`."""
    # Given Pinecone cannot be reached
    original = PineconeConnectionError("connection refused")
    # When the index is ensured / Then the leaf error is raised and the cause is kept
    with pytest.raises(VectorStoreUnreachableError) as caught:
        ensure_index(make_settings(), StubPineconeClient(error=original))
    assert caught.value.__cause__ is original


def test_ensure_chains_auth_error_as_authentication(make_settings) -> None:
    """VC-012: authentication error → VectorStoreAuthenticationError with the original as `__cause__`."""
    # Given Pinecone rejects the key
    original = UnauthorizedError()
    # When the index is ensured / Then the leaf error is raised and the cause is kept
    with pytest.raises(VectorStoreAuthenticationError) as caught:
        ensure_index(make_settings(), StubPineconeClient(error=original))
    assert caught.value.__cause__ is original


# --- client factory -----------------------------------------------------------------------------


def test_pinecone_client_builds_offline_and_hides_the_key(make_settings) -> None:
    """BR-003: building the client makes no network call and its repr shows no key."""
    # Given fake settings / When the client is built (sockets are blocked by the harness)
    client = make_pinecone_client(make_settings())
    # Then it exists and does not show the key
    assert FAKE_PINECONE_KEY not in repr(client)
