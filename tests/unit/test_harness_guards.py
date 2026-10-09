"""The offline harness really is offline and never reads the real `.env` (VC-040, VC-040a)."""

import socket
from pathlib import Path

import pytest

from services.settings import ENV_FILE, load_environment



def test_outbound_connection_fails_during_offline_tests() -> None:
    """VC-040 (partial): any socket connect raises inside the default test run."""
    with pytest.raises(RuntimeError, match="Network access"):
        socket.create_connection(("127.0.0.1", 9), timeout=1)


def test_loading_the_real_env_file_fails() -> None:
    """VC-040a: the repository-root .env can never be loaded by a test."""
    with pytest.raises(RuntimeError, match="real .env"):
        load_environment(ENV_FILE)


def test_loading_the_default_env_file_fails() -> None:
    """VC-040a: the default path (what the app uses) is the real .env, so it is refused too."""
    with pytest.raises(RuntimeError, match="real .env"):
        load_environment()


def test_loading_a_temporary_env_file_works(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """VC-040a: tests may load fixture env files they create themselves."""
    env_file = tmp_path / ".env"
    env_file.write_text("OCTI_FIXTURE_ONLY=yes\n")
    monkeypatch.delenv("OCTI_FIXTURE_ONLY", raising=False)
    assert load_environment(env_file) is True
    monkeypatch.delenv("OCTI_FIXTURE_ONLY")
