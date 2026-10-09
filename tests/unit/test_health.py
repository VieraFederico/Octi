"""Service check logic (spec FR-008, FR-015 … FR-018, BR-003, BR-007)."""

import subprocess

import openai
import pytest
from langsmith.utils import LangSmithAuthError
from pinecone import PineconeConnectionError

from services.errors import (
    EmbeddingDimensionError,
    InvalidSettingsError,
    ModelNotAvailableError,
    ProxyAuthenticationError,
    ProxyUnreachableError,
    TracingAuthenticationError,
)
from services.health import (
    SERVICE_CHECKS,
    CheckResult,
    check_chat,
    check_embeddings,
    check_git_tracking,
    check_langsmith,
    check_models,
    check_pinecone,
    run_checks,
)
from services.settings import Settings
from tests.fakes import (
    FAKE_LITELLM_KEY,
    GIT_NOT_A_REPOSITORY,
    GIT_NOT_TRACKED,
    GIT_TRACKED,
    MODEL_IDS,
    StubChatModel,
    StubEmbeddings,
    StubLangSmithClient,
    StubPineconeClient,
    always,
    failing,
    healthy_clients,
    openai_connection_error,
    openai_status_error,
)


def by_name(results: list[CheckResult]) -> dict[str, CheckResult]:
    return {result.name: result for result in results}


# --- One check at a time -------------------------------------------------------------------------


def test_models_ok_when_both_ids_are_listed(make_settings) -> None:
    """VC-019: the proxy lists LLM_MODEL and EMBEDDING_MODEL → models OK."""
    assert check_models(make_settings(), lambda _settings: MODEL_IDS).status == "OK"


def test_models_fail_naming_the_missing_id(make_settings) -> None:
    """VC-019a: the proxy list lacks LLM_MODEL → ModelNotAvailableError naming that id only."""
    with pytest.raises(ModelNotAvailableError) as caught:
        check_models(make_settings(), lambda _settings: ["fake-embedding-model"])
    assert "fake-chat-model" in caught.value.user_message
    assert "fake-embedding-model" not in caught.value.user_message


def test_chat_connection_error_is_proxy_unreachable(make_settings) -> None:
    """VC-012a: chat stub raising a connection error → ProxyUnreachableError with the cause chained."""
    error = openai_connection_error()
    with pytest.raises(ProxyUnreachableError) as caught:
        check_chat(make_settings(), always(StubChatModel(error=error)))
    assert caught.value.__cause__ is error


def test_chat_401_is_proxy_authentication(make_settings) -> None:
    """VC-012a: a 401 from the proxy → ProxyAuthenticationError."""
    with pytest.raises(ProxyAuthenticationError):
        check_chat(make_settings(), always(StubChatModel(error=openai_status_error(openai.AuthenticationError, 401))))


def test_chat_sends_one_short_prompt(make_settings) -> None:
    """FR-015: the chat check makes exactly one minimal completion."""
    chat = StubChatModel()
    assert check_chat(make_settings(), always(chat)).status == "OK"
    assert len(chat.prompts) == 1


def test_embeddings_ok_with_the_expected_length(make_settings) -> None:
    """VC-019: the embedding has EMBEDDING_DIMENSION numbers → OK."""
    assert check_embeddings(make_settings(), always(StubEmbeddings(1536))).status == "OK"


def test_embeddings_fail_on_the_wrong_length(make_settings) -> None:
    """VC-020: a 3072-length vector → EmbeddingDimensionError mentioning expected 1536."""
    with pytest.raises(EmbeddingDimensionError) as caught:
        check_embeddings(make_settings(), always(StubEmbeddings(3072)))
    assert "1536" in caught.value.user_message
    assert "3072" in caught.value.user_message


def test_pinecone_uses_the_index_status(make_settings) -> None:
    """FR-015: Pinecone OK for a matching index; FAIL with the status reason otherwise."""
    settings = make_settings()
    assert check_pinecone(settings, always(StubPineconeClient(index=(1536, "cosine")))).status == "OK"
    missing = check_pinecone(settings, always(StubPineconeClient(index=None)))
    assert missing.status == "FAIL"
    assert "python -m scripts.setup_index" in missing.reason
    unreachable = check_pinecone(settings, always(StubPineconeClient(error=PineconeConnectionError("x"))))
    assert unreachable.status == "FAIL"


def test_langsmith_ok_when_tracing_is_on_and_key_works(make_settings) -> None:
    """VC-019: tracing on and an authenticated request succeeds → OK."""
    settings = make_settings(LANGSMITH_TRACING="true")
    assert check_langsmith(settings, always(StubLangSmithClient())).status == "OK"


def test_langsmith_fails_when_tracing_is_off_without_building_a_client(make_settings) -> None:
    """D-024: tracing off → LangSmith FAIL telling how to turn it on; no client is built."""
    result = check_langsmith(make_settings(LANGSMITH_TRACING="false"), failing(AssertionError("must not build")))
    assert result.status == "FAIL"
    assert "LANGSMITH_TRACING" in result.reason


def test_langsmith_rejected_key_is_tracing_authentication(make_settings) -> None:
    """FR-008: LangSmith rejects the key → TracingAuthenticationError."""
    error = LangSmithAuthError("Authentication failed")
    with pytest.raises(TracingAuthenticationError):
        check_langsmith(make_settings(LANGSMITH_TRACING="true"), always(StubLangSmithClient(error=error)))


def test_git_ok_when_secrets_file_is_not_tracked() -> None:
    """FR-016: not tracked → OK."""
    assert check_git_tracking(GIT_NOT_TRACKED).status == "OK"


def test_git_fails_when_secrets_file_is_tracked() -> None:
    """VC-021: tracked → FAIL telling the user to untrack it."""
    result = check_git_tracking(GIT_TRACKED)
    assert result.status == "FAIL"
    assert "git rm --cached" in result.reason


def test_git_skipped_outside_a_repository() -> None:
    """VC-021a: not a git repository → skipped (not a git repository)."""
    result = check_git_tracking(GIT_NOT_A_REPOSITORY)
    assert result.status == "SKIPPED"
    assert result.line().endswith("skipped (not a git repository)")


def test_git_skipped_when_git_is_not_installed() -> None:
    """FR-016: no git program → skipped, never a crash."""

    def no_git(_args: list[str]) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("git")

    assert check_git_tracking(no_git).status == "SKIPPED"


def test_git_is_asked_about_the_secrets_file_only() -> None:
    """FR-016: git gets a fixed argument list (no shell) ending with the secrets file name."""
    seen: list[list[str]] = []

    def record(args: list[str]) -> subprocess.CompletedProcess[str]:
        seen.append(args)
        return GIT_NOT_TRACKED(args)

    check_git_tracking(record)
    assert seen == [["git", "ls-files", "--error-unmatch", "--", ".env"]]


def test_result_lines_have_the_documented_format() -> None:
    """FR-015: lines read `<name>: OK`, `<name>: FAIL: <reason>`, `<name>: skipped (<reason>)`."""
    assert CheckResult("chat", "OK").line() == "chat: OK"
    assert CheckResult("chat", "FAIL", "proxy down").line() == "chat: FAIL: proxy down"
    assert CheckResult("git", "SKIPPED", "not a git repository").line() == "git: skipped (not a git repository)"


# --- The whole run -------------------------------------------------------------------------------


def test_all_healthy_gives_ok_for_every_check(make_settings) -> None:
    """VC-019: all stubs healthy → OK for configuration, models, chat, embeddings, Pinecone, LangSmith (and git)."""
    results = run_checks(lambda: make_settings(LANGSMITH_TRACING="true"), healthy_clients())
    assert [result.name for result in results] == ["configuration", *SERVICE_CHECKS, "git"]
    assert {result.status for result in results} == {"OK"}


def test_a_failing_check_does_not_stop_the_others(make_settings) -> None:
    """VC-022 / VC-012a: chat raises → chat FAIL with the leaf's message; every other check still OK."""
    clients = healthy_clients(chat_model=always(StubChatModel(error=openai_connection_error())))
    results = by_name(run_checks(lambda: make_settings(LANGSMITH_TRACING="true"), clients))
    assert results["chat"].status == "FAIL"
    assert results["chat"].reason.startswith("Could not reach the LiteLLM proxy")
    assert {results[name].status for name in ("models", "embeddings", "pinecone", "langsmith", "git")} == {"OK"}


def test_a_client_that_cannot_be_built_fails_only_its_own_check(make_settings) -> None:
    """VC-022a: building the LangSmith client raises → only langsmith fails; the other stubs are still called."""
    chat, embeddings, index = StubChatModel(), StubEmbeddings(), StubPineconeClient(index=(1536, "cosine"))
    clients = healthy_clients(
        chat_model=always(chat),
        embeddings=always(embeddings),
        pinecone=always(index),
        langsmith=failing(RuntimeError("cannot build the client")),
    )
    results = by_name(run_checks(lambda: make_settings(LANGSMITH_TRACING="true"), clients))
    assert results["langsmith"].status == "FAIL"
    assert {results[name].status for name in ("models", "chat", "embeddings", "pinecone")} == {"OK"}
    assert chat.prompts and embeddings.texts and index.calls


def test_invalid_configuration_skips_the_service_checks() -> None:
    """VC-023: invalid configuration → configuration FAIL naming fields; service checks skipped; git still runs."""

    def broken() -> Settings:
        raise InvalidSettingsError({"LITELLM_API_KEY": "missing", "LLM_MODEL": "missing"})

    results = by_name(run_checks(broken, healthy_clients()))
    assert results["configuration"].status == "FAIL"
    assert "LITELLM_API_KEY" in results["configuration"].reason
    assert "LLM_MODEL" in results["configuration"].reason
    assert {results[name].status for name in SERVICE_CHECKS} == {"SKIPPED"}
    assert results["git"].status == "OK"


def test_unexpected_exceptions_never_show_their_text(make_settings) -> None:
    """VC-024: a stub raising a non-library exception that contains a key → FAIL without the key."""
    clients = healthy_clients(embeddings=always(StubEmbeddings(error=RuntimeError(f"boom {FAKE_LITELLM_KEY}"))))
    results = by_name(run_checks(lambda: make_settings(LANGSMITH_TRACING="true"), clients))
    assert results["embeddings"].status == "FAIL"
    assert FAKE_LITELLM_KEY not in results["embeddings"].reason
    assert "RuntimeError" in results["embeddings"].reason
