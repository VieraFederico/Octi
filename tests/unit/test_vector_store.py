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
    delete_records,
    ensure_index,
    find_versions,
    list_records,
    make_pinecone_client,
    open_index,
    upsert_records,
)
from tests.stubs import FAKE_PINECONE_KEY, FakePineconeIndex, StubPineconeClient

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


# --- Records: list, find, upsert, delete (spec 01 FR-138, FR-149; agent-agnostic, D-084) -----------

NAMESPACE = "octi"


def record(n: int, source_file: str = "report.pdf", sha: str = "sha-1") -> dict:
    """An Index record as `upsert_records` takes it."""
    table_id = f"{n:016x}-p1-t1"
    return {
        "id": table_id,
        "values": [0.1, 0.2],
        "metadata": {"table_id": table_id, "source_file": source_file, "document_sha": sha},
    }


def test_open_index_uses_the_host_pinecone_reports(make_settings) -> None:
    """The index handle comes from the client: the index's host is looked up, then opened."""
    # Given a client that knows the index and hands out an index object for a host
    fake = FakePineconeIndex()
    client = StubPineconeClient(index=(1536, "cosine"))
    client.opened_index = fake
    # When the index is opened
    index = open_index(make_settings(), client)
    # Then it is the object for the host Pinecone reported
    assert index is fake
    assert client.opened_hosts == ["stub-host.example.test"]


def test_open_index_of_a_missing_index_is_unreachable(make_settings) -> None:
    """No index to open: the failure is a vector store error, not a raw SDK one."""
    with pytest.raises(VectorStoreUnreachableError):
        open_index(make_settings(), StubPineconeClient(index=None))


def test_upsert_sends_batches_of_100(make_settings) -> None:
    """VC-140 / FR-138: 250 records go up as 100, 100 and 50."""
    index = FakePineconeIndex()
    upsert_records(index, NAMESPACE, [record(n) for n in range(250)])
    assert index.upsert_batches == [100, 100, 50]
    assert len(index.ids(NAMESPACE)) == 250


def test_upserting_the_same_ids_again_overwrites(make_settings) -> None:
    """BR-104: the same ids leave the same record count."""
    index = FakePineconeIndex()
    upsert_records(index, NAMESPACE, [record(n) for n in range(5)])
    upsert_records(index, NAMESPACE, [record(n) for n in range(5)])
    assert len(index.ids(NAMESPACE)) == 5


def test_list_records_returns_every_metadata_dict_across_pages(make_settings) -> None:
    """FR-149: ids are listed page by page, then fetched in batches; the result is the metadata."""
    # Given 230 records and a listing that returns 100 ids per page
    index = FakePineconeIndex()
    upsert_records(index, NAMESPACE, [record(n) for n in range(230)])
    index.calls.clear()
    # When they are listed
    records = list_records(index, NAMESPACE)
    # Then every record's metadata comes back, fetched in batches of 100
    assert len(records) == 230
    assert {r["table_id"] for r in records} == set(index.ids(NAMESPACE))
    assert index.calls.count("fetch") == 3


def test_list_records_on_an_empty_namespace_is_empty() -> None:
    assert list_records(FakePineconeIndex(), NAMESPACE) == []


def test_find_versions_filters_by_file_name_and_follows_pages() -> None:
    """FR-138 step 4 / A-103: only the records with that `source_file`, all pages."""
    # Given 5 records of report.pdf and 2 of other.pdf, and pages of 2
    index = FakePineconeIndex(page_size=2)
    upsert_records(index, NAMESPACE, [record(n) for n in range(5)])
    upsert_records(index, NAMESPACE, [record(n, source_file="other.pdf") for n in range(10, 12)])
    # When the versions of report.pdf are searched
    found = find_versions(index, NAMESPACE, "report.pdf")
    # Then exactly its 5 records are found
    assert len(found) == 5
    assert {r["source_file"] for r in found} == {"report.pdf"}


def test_delete_removes_the_ids(make_settings) -> None:
    index = FakePineconeIndex()
    upsert_records(index, NAMESPACE, [record(n) for n in range(5)])
    delete_records(index, NAMESPACE, [record(0)["id"], record(1)["id"]])
    assert len(index.ids(NAMESPACE)) == 3


def test_delete_with_no_ids_makes_no_call() -> None:
    index = FakePineconeIndex()
    delete_records(index, NAMESPACE, [])
    assert index.calls == []


@pytest.mark.parametrize(
    ("call", "failing_method"),
    [
        (lambda index: list_records(index, NAMESPACE), "list"),
        (lambda index: find_versions(index, NAMESPACE, "report.pdf"), "fetch_by_metadata"),
        (lambda index: upsert_records(index, NAMESPACE, [record(1)]), "upsert"),
        (lambda index: delete_records(index, NAMESPACE, ["x"]), "delete"),
    ],
    ids=["list_records", "find_versions", "upsert_records", "delete_records"],
)
def test_pinecone_failures_become_vector_store_errors(call, failing_method: str) -> None:
    """FR-008 / VC-172 (data part): a failing call raises a leaf error with the original as its cause."""
    # Given an index whose call fails with a connection error
    original = PineconeConnectionError("connection refused")
    index = FakePineconeIndex(fail_on=failing_method, error=original)
    # When the function is called
    with pytest.raises(VectorStoreUnreachableError) as caught:
        call(index)
    # Then the error is translated, chained to the original, and says nothing raw
    assert caught.value.__cause__ is original
    assert "refused" not in caught.value.user_message


def test_a_failure_while_fetching_a_listed_batch_is_translated_too() -> None:
    index = FakePineconeIndex(fail_on="fetch")
    upsert_records(index, NAMESPACE, [record(1)])
    with pytest.raises(VectorStoreUnreachableError):
        list_records(index, NAMESPACE)


def test_authentication_failures_are_translated_too() -> None:
    index = FakePineconeIndex(fail_on="upsert", error=UnauthorizedError("bad key"))
    with pytest.raises(VectorStoreAuthenticationError):
        upsert_records(index, NAMESPACE, [record(1)])
