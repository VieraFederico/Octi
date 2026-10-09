"""Factories for the models behind the university LiteLLM proxy (BR-001).

Every chat and embedding call in Octi uses an object built here, so the proxy URL, model names,
timeout and retry policy are set in exactly one place. The proxy speaks the OpenAI API, which is why
`langchain_openai` is used even though the models behind it may come from other vendors.

Retries: the OpenAI client already retries connection errors, timeouts, 408, 409, 429 and >= 500 with
exponential backoff and jitter. `max_retries=2` means 3 attempts in total (D-021). Octi adds no retry
loop of its own (BR-006, D-026), so the factories return the LangChain objects as they are.

The API key is passed as the `SecretStr` from `Settings`: LangChain keeps it masked, so Octi never
unwraps it here. Factory idea adapted from the course's Lab 01 (Knowledge) — see README › Credits.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager

import openai
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from services.errors import ModelNotAvailableError, ProxyAuthenticationError, ProxyUnreachableError
from services.settings import Settings

logger = logging.getLogger(__name__)

_AUTH_MESSAGE = "The LiteLLM proxy rejected the API key. Check LITELLM_API_KEY in .env."
_MODEL_MESSAGE = "The LiteLLM proxy does not offer the requested model. Check LLM_MODEL and EMBEDDING_MODEL in .env."
_UNREACHABLE_MESSAGE = (
    "Could not reach the LiteLLM proxy, or it did not answer in time. Check your connection and LITELLM_BASE_URL."
)
_FAILED_MESSAGE = "The LiteLLM proxy could not complete the request (HTTP {status}). Try again later."


def make_chat_model(settings: Settings) -> ChatOpenAI:
    """A chat model on the proxy, configured entirely from `settings` (FR-005)."""
    return ChatOpenAI(
        base_url=settings.LITELLM_BASE_URL,
        api_key=settings.LITELLM_API_KEY,
        model=settings.LLM_MODEL,
        temperature=settings.LLM_TEMPERATURE,
        timeout=settings.LLM_TIMEOUT_SECONDS,
        max_retries=settings.LLM_MAX_RETRIES,
    )


def make_embeddings(settings: Settings) -> OpenAIEmbeddings:
    """An embedding model on the proxy, with the same timeout and retry policy (FR-006)."""
    return OpenAIEmbeddings(
        base_url=settings.LITELLM_BASE_URL,
        api_key=settings.LITELLM_API_KEY,
        model=settings.EMBEDDING_MODEL,
        # LangChain normally turns text into OpenAI token ids before sending it. The proxy may route
        # to a non-OpenAI model that expects plain strings, so that step is switched off.
        check_embedding_ctx_length=False,
        timeout=settings.LLM_TIMEOUT_SECONDS,
        max_retries=settings.LLM_MAX_RETRIES,
    )


def list_proxy_models(settings: Settings) -> list[str]:
    """The model ids the proxy offers (`GET /v1/models`), asked through the chat model's own client."""
    return [model.id for model in make_chat_model(settings).root_client.models.list()]


@contextmanager
def translate_proxy_errors() -> Iterator[None]:
    """Turn openai client errors into LiteLLM leaf errors, keeping the original as `__cause__` (FR-008).

    By the time an error arrives here the client has already retried what is worth retrying.
    The raw error (which may include the proxy's response body) is only logged at DEBUG level.
    """
    try:
        yield
    except (openai.AuthenticationError, openai.PermissionDeniedError) as exc:
        logger.debug("LiteLLM rejected the credentials", exc_info=True)
        raise ProxyAuthenticationError(_AUTH_MESSAGE) from exc
    except openai.NotFoundError as exc:
        logger.debug("LiteLLM model not found", exc_info=True)
        raise ModelNotAvailableError(_MODEL_MESSAGE) from exc
    except openai.APIConnectionError as exc:  # also covers APITimeoutError, its subclass
        logger.debug("LiteLLM could not be reached", exc_info=True)
        raise ProxyUnreachableError(_UNREACHABLE_MESSAGE) from exc
    except openai.APIError as exc:
        # Any other HTTP status (400, 429 after retries, 5xx): only the status code is shown.
        logger.debug("LiteLLM request failed", exc_info=True)
        status = getattr(exc, "status_code", "unknown")
        raise ProxyUnreachableError(_FAILED_MESSAGE.format(status=status)) from exc
