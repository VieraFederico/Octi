"""Service-check script: `python -m scripts.check_services` (spec FR-015 … FR-018, BR-003, BR-007)."""

import openai
import pytest

from scripts.check_services import main
from services.errors import InvalidSettingsError
from services.settings import Settings
from tests.stubs import (
    FAKE_LITELLM_KEY,
    FAKE_PINECONE_KEY,
    GIT_NOT_A_REPOSITORY,
    StubChatModel,
    StubEmbeddings,
    always,
    healthy_clients,
    openai_status_error,
)


def test_all_healthy_prints_ok_lines_and_exits_zero(make_settings, capsys: pytest.CaptureFixture[str]) -> None:
    """VC-019: every check OK → one `OK` line per check, exit 0."""
    exit_code = main(lambda: make_settings(LANGSMITH_TRACING="true"), healthy_clients())
    assert exit_code == 0
    assert capsys.readouterr().out.splitlines() == [
        "configuration: OK",
        "models: OK",
        "chat: OK",
        "embeddings: OK",
        "pinecone: OK",
        "langsmith: OK",
        "git: OK",
    ]


def test_one_failure_exits_non_zero_but_prints_every_line(make_settings, capsys: pytest.CaptureFixture[str]) -> None:
    """VC-022: chat fails → chat FAIL line, the other lines still printed, exit non-zero."""
    clients = healthy_clients(chat_model=always(StubChatModel(error=openai_status_error(openai.AuthenticationError, 401))))
    exit_code = main(lambda: make_settings(LANGSMITH_TRACING="true"), clients)
    lines = capsys.readouterr().out.splitlines()
    assert exit_code != 0
    assert len(lines) == 7
    assert lines[2].startswith("chat: FAIL: ")


def test_invalid_configuration_exits_non_zero(capsys: pytest.CaptureFixture[str]) -> None:
    """VC-023: invalid configuration → configuration FAIL naming fields, service lines skipped, exit non-zero."""

    def broken() -> Settings:
        raise InvalidSettingsError({"PINECONE_API_KEY": "missing"})

    exit_code = main(broken, healthy_clients())
    output = capsys.readouterr().out
    assert exit_code != 0
    assert "configuration: FAIL:" in output and "PINECONE_API_KEY" in output
    assert "chat: skipped (configuration is invalid)" in output


def test_git_skip_does_not_change_the_exit_code(make_settings, capsys: pytest.CaptureFixture[str]) -> None:
    """VC-021a: not a git repository → `git: skipped (not a git repository)` and exit 0 when all else is OK."""
    exit_code = main(lambda: make_settings(LANGSMITH_TRACING="true"), healthy_clients(run_git=GIT_NOT_A_REPOSITORY))
    assert exit_code == 0
    assert "git: skipped (not a git repository)" in capsys.readouterr().out


def test_tracing_off_makes_the_run_fail(make_settings, capsys: pytest.CaptureFixture[str]) -> None:
    """D-024: tracing off → LangSmith FAIL, exit non-zero."""
    exit_code = main(lambda: make_settings(LANGSMITH_TRACING="false"), healthy_clients())
    assert exit_code != 0
    assert "langsmith: FAIL:" in capsys.readouterr().out


def test_no_secret_reaches_the_output(make_settings, capsys: pytest.CaptureFixture[str]) -> None:
    """VC-024: stubs raising exceptions that contain keys → output contains no key and no raw library text."""
    auth_error = openai_status_error(openai.AuthenticationError, 401, f"Invalid key {FAKE_LITELLM_KEY}")
    clients = healthy_clients(
        chat_model=always(StubChatModel(error=auth_error)),
        embeddings=always(StubEmbeddings(error=RuntimeError(f"leak {FAKE_PINECONE_KEY}"))),
    )
    main(lambda: make_settings(LANGSMITH_TRACING="true"), clients)
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert FAKE_LITELLM_KEY not in output
    assert FAKE_PINECONE_KEY not in output
    assert "Invalid key" not in output
