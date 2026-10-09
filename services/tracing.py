"""LangSmith: the client factory and the error translation.

Named `tracing` (not `langsmith`) so it does not shadow the `langsmith` library.

Agent runs are traced through environment variables that LangChain reads by itself (`LANGSMITH_*`);
this client is only needed to talk to LangSmith directly, e.g. to check that the key works.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from langsmith import Client as LangSmithClient
from langsmith.utils import LangSmithAuthError, LangSmithError

from services.errors import TracingAuthenticationError, TracingUnreachableError
from services.settings import Settings

logger = logging.getLogger(__name__)

_AUTH_MESSAGE = "LangSmith rejected the API key. Check LANGSMITH_API_KEY (and LANGSMITH_WORKSPACE_ID) in .env."
_UNREACHABLE_MESSAGE = (
    "Could not reach LangSmith, or it did not answer in time. Check your connection and LANGSMITH_ENDPOINT."
)


def make_langsmith_client(settings: Settings) -> LangSmithClient:
    """A LangSmith client. Note: building it already sends one request (`GET /info`)."""
    api_key = settings.LANGSMITH_API_KEY.get_secret_value() if settings.LANGSMITH_API_KEY else None
    return LangSmithClient(
        api_url=settings.LANGSMITH_ENDPOINT,
        api_key=api_key,
        workspace_id=settings.LANGSMITH_WORKSPACE_ID or None,
        timeout_ms=settings.LLM_TIMEOUT_SECONDS * 1000,
    )


@contextmanager
def translate_tracing_errors() -> Iterator[None]:
    """Turn LangSmith errors into tracing leaf errors, keeping the original as `__cause__` (FR-008)."""
    try:
        yield
    except LangSmithAuthError as exc:
        logger.debug("LangSmith rejected the credentials", exc_info=True)
        raise TracingAuthenticationError(_AUTH_MESSAGE) from exc
    except LangSmithError as exc:  # connection errors, timeouts and every other LangSmith failure
        logger.debug("LangSmith request failed", exc_info=True)
        raise TracingUnreachableError(_UNREACHABLE_MESSAGE) from exc
