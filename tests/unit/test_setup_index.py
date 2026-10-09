"""Setup script: `python -m scripts.setup_index` (spec FR-008, FR-011 … FR-013, BR-007)."""

import pytest
from pinecone import PineconeConnectionError, UnauthorizedError

from scripts.setup_index import main
from tests.stubs import FAKE_PINECONE_KEY, StubPineconeClient


def test_creates_missing_index_and_says_created(make_settings, capsys: pytest.CaptureFixture[str]) -> None:
    """VC-015: no index → it is created, the output says "created", exit 0."""
    # Given Pinecone has no index
    client = StubPineconeClient(index=None)
    # When the script runs
    exit_code = main(settings=make_settings(), client=client)
    # Then it created the index and said so
    assert exit_code == 0
    assert client.write_calls == ["create_index"]
    assert "created" in capsys.readouterr().out


def test_existing_index_is_left_alone(make_settings, capsys: pytest.CaptureFixture[str]) -> None:
    """VC-016: matching index → no create/delete call, "already exists", exit 0."""
    # Given a matching index
    client = StubPineconeClient(index=(1536, "cosine"))
    # When the script runs
    exit_code = main(settings=make_settings(), client=client)
    # Then nothing changed and it said so
    assert exit_code == 0
    assert client.write_calls == []
    assert "already exists" in capsys.readouterr().out


def test_mismatched_index_exits_non_zero_with_expected_and_actual(
    make_settings, capsys: pytest.CaptureFixture[str]
) -> None:
    """VC-017 / VC-012: dimension 3072 → no writes, non-zero exit, output shows expected 1536 and actual 3072."""
    # Given an index with 3072 dimensions
    client = StubPineconeClient(index=(3072, "cosine"))
    # When the script runs
    exit_code = main(settings=make_settings(), client=client)
    # Then it changed nothing, failed, and showed both shapes
    output = capsys.readouterr().err
    assert exit_code != 0
    assert client.write_calls == []
    assert "expected 1536" in output
    assert "actual 3072" in output


@pytest.mark.parametrize(
    "error",
    [PineconeConnectionError("connection refused"), UnauthorizedError(f"bad key {FAKE_PINECONE_KEY}")],
)
def test_service_failure_prints_only_the_safe_message(
    make_settings, capsys: pytest.CaptureFixture[str], error: Exception
) -> None:
    """VC-012 / BR-007: a connection or auth failure → non-zero exit, only the leaf's user_message is shown."""
    # Given Pinecone fails (the auth error message even echoes the key)
    client = StubPineconeClient(error=error)
    # When the script runs
    exit_code = main(settings=make_settings(), client=client)
    # Then it fails with a safe message: no raw library text, no key
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert exit_code != 0
    assert output.strip()
    assert str(error) not in output
    assert FAKE_PINECONE_KEY not in output


def test_invalid_settings_exit_non_zero_naming_the_variable(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, fake_env: dict[str, str]
) -> None:
    """FR-002 / BR-007: missing configuration → non-zero exit, the variable is named, no traceback."""
    # Given get_settings() fails because PINECONE_API_KEY is missing
    from services.settings import Settings

    def broken_settings() -> Settings:
        environment = dict(fake_env)
        environment.pop("PINECONE_API_KEY")
        return Settings.from_mapping(environment)

    monkeypatch.setattr("scripts.setup_index.get_settings", broken_settings)
    # When the script runs without injected settings
    exit_code = main(client=StubPineconeClient(index=None))
    # Then it fails and names the variable
    output = capsys.readouterr().err
    assert exit_code != 0
    assert "PINECONE_API_KEY" in output
    assert "Traceback" not in output
