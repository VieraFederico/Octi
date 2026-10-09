"""Model factories: chat and embeddings behind the LiteLLM proxy (spec FR-005, FR-006, BR-001, BR-006)."""

import httpx2
import openai
import pytest
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from services.errors import ModelNotAvailableError, ProxyAuthenticationError, ProxyUnreachableError
from services.llm import make_chat_model, make_embeddings, translate_proxy_errors
from tests.fakes import FAKE_LITELLM_KEY, openai_connection_error, openai_status_error


def test_chat_model_uses_every_setting(make_settings) -> None:
    """VC-008: base URL, model, temperature 0, timeout 60 and max retries 2 come from Settings."""
    # Given default fake settings / When the chat factory runs (no network: nothing is called)
    model = make_chat_model(make_settings())
    # Then the object carries the configured values
    assert model.openai_api_base == "https://proxy.example.test/v1"
    assert model.model_name == "fake-chat-model"
    assert model.temperature == 0.0
    assert model.request_timeout == 60
    assert model.max_retries == 2


def test_chat_model_follows_overridden_settings(make_settings) -> None:
    """VC-008: non-default values flow through unchanged."""
    # Given non-default temperature, timeout and retries
    settings = make_settings(LLM_TEMPERATURE="0.7", LLM_TIMEOUT_SECONDS="15", LLM_MAX_RETRIES="0")
    # When the chat factory runs
    model = make_chat_model(settings)
    # Then the object reflects them
    assert model.temperature == 0.7
    assert model.request_timeout == 15
    assert model.max_retries == 0


def test_embeddings_use_proxy_model_and_plain_strings(make_settings) -> None:
    """VC-009: base URL and model match Settings; client-side tokenization is disabled."""
    # Given default fake settings / When the embeddings factory runs
    embeddings = make_embeddings(make_settings())
    # Then it targets the proxy with the configured model and sends plain strings
    assert embeddings.openai_api_base == "https://proxy.example.test/v1"
    assert embeddings.model == "fake-embedding-model"
    assert embeddings.check_embedding_ctx_length is False


def test_every_model_points_at_the_proxy(make_settings) -> None:
    """VC-010: every object the factories produce points at LITELLM_BASE_URL."""
    # Given a proxy URL written without /v1
    settings = make_settings(LITELLM_BASE_URL="https://other-proxy.example.test")
    # When both factories run
    models = [make_chat_model(settings), make_embeddings(settings)]
    # Then both use the normalised proxy URL
    assert {model.openai_api_base for model in models} == {"https://other-proxy.example.test/v1"}


def test_both_models_carry_retry_count_and_timeout(make_settings) -> None:
    """VC-010a: both outputs use the retry count and timeout from Settings (2 retries = 3 attempts, 60 s)."""
    # Given default fake settings / When both factories run
    settings = make_settings()
    chat, embeddings = make_chat_model(settings), make_embeddings(settings)
    # Then the OpenAI clients underneath carry the same policy
    assert chat.root_client.max_retries == 2
    assert chat.root_client.timeout == 60
    assert embeddings.max_retries == 2
    assert embeddings.request_timeout == 60


def test_factories_add_no_second_retry_loop(make_settings) -> None:
    """VC-010a: the factories return the LangChain objects themselves, not a retry wrapper."""
    # Given default fake settings / When both factories run
    settings = make_settings()
    # Then the exact LangChain classes come back (a `.with_retry()` wrapper would be a different type)
    assert type(make_chat_model(settings)) is ChatOpenAI
    assert type(make_embeddings(settings)) is OpenAIEmbeddings


def test_models_never_show_the_api_key(make_settings) -> None:
    """BR-003: the key stays masked in the objects' text form."""
    # Given default fake settings / When both factories run
    settings = make_settings()
    # Then the fake key never appears in their repr
    for model in (make_chat_model(settings), make_embeddings(settings)):
        assert FAKE_LITELLM_KEY not in repr(model)


@pytest.mark.parametrize(
    ("error", "leaf"),
    [
        (openai_connection_error(), ProxyUnreachableError),
        (openai.APITimeoutError(request=httpx2.Request("POST", "https://proxy.example.test")), ProxyUnreachableError),
        (openai_status_error(openai.AuthenticationError, 401), ProxyAuthenticationError),
        (openai_status_error(openai.PermissionDeniedError, 403), ProxyAuthenticationError),
        (openai_status_error(openai.NotFoundError, 404), ModelNotAvailableError),
        (openai_status_error(openai.InternalServerError, 500), ProxyUnreachableError),
    ],
)
def test_proxy_errors_become_leaves_with_the_cause_kept(error: Exception, leaf: type[Exception]) -> None:
    """FR-008: each openai error becomes the matching leaf, original chained as `__cause__`."""
    # Given a block that raises an openai error / When it runs inside the translator
    with pytest.raises(leaf) as caught, translate_proxy_errors():
        raise error
    # Then the leaf keeps the original as its cause
    assert caught.value.__cause__ is error


def test_unexpected_status_shows_only_the_code() -> None:
    """BR-007: an unmapped HTTP error shows its status code, never the proxy's raw body."""
    error = openai_status_error(openai.BadRequestError, 400, f"raw body {FAKE_LITELLM_KEY}")
    with pytest.raises(ProxyUnreachableError) as caught, translate_proxy_errors():
        raise error
    assert "HTTP 400" in caught.value.user_message
    assert FAKE_LITELLM_KEY not in caught.value.user_message
