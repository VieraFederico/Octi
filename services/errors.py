"""Octi's error tree (decision D-027).

Abstract bases only *group* errors so callers can write `except VectorStoreError`; they can never be
instantiated. Code always raises a *leaf* that names exactly what happened and carries a
`user_message` that is safe to show in the UI. The original library exception is chained with
`raise Leaf(...) from exc`, so logs keep the details while the UI never shows them.

    AppError
    ├── ConfigurationError
    │   └── InvalidSettingsError
    └── ExternalServiceError            (.service)
        ├── LLMProxyError               (LiteLLM: chat + embeddings)
        │   ├── ProxyUnreachableError
        │   ├── ProxyAuthenticationError
        │   ├── ModelNotAvailableError
        │   └── EmbeddingDimensionError
        ├── VectorStoreError            (Pinecone)
        │   ├── VectorStoreUnreachableError
        │   ├── VectorStoreAuthenticationError
        │   ├── IndexNotFoundError
        │   └── IndexMismatchError
        └── TracingError                (LangSmith)
            ├── TracingUnreachableError
            └── TracingAuthenticationError

Rule (BR-011): add a new leaf only when code or UI must react differently, or the user message differs.
"""

from collections.abc import Mapping
from typing import Any, ClassVar


class AppError(Exception):
    """Root of every error Octi raises on purpose. Abstract."""

    _abstract: ClassVar[bool] = True

    def __new__(cls, *args: Any, **kwargs: Any) -> "AppError":
        # `cls.__dict__` (not getattr) so a leaf does not inherit its parent's abstract flag.
        if cls.__dict__.get("_abstract", False):
            raise TypeError(f"{cls.__name__} is an abstract base error; raise one of its leaf classes")
        return super().__new__(cls)

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


# --- Configuration -----------------------------------------------------------------------------


class ConfigurationError(AppError):
    """Octi's own configuration is wrong. Abstract."""

    _abstract = True


class InvalidSettingsError(ConfigurationError):
    """One or more environment variables are missing or invalid.

    `problems` maps each variable name to a reason ("missing" or what rule it broke). Values are never
    stored, so the error is always safe to print.
    """

    def __init__(self, problems: Mapping[str, str]) -> None:
        self.problems = dict(problems)
        details = "; ".join(f"{name} ({reason})" for name, reason in self.problems.items())
        super().__init__(f"Some settings are missing or invalid: {details}.")

    @property
    def fields(self) -> tuple[str, ...]:
        return tuple(self.problems)


# --- External services -------------------------------------------------------------------------


class ExternalServiceError(AppError):
    """A service Octi depends on failed. Abstract. Subclasses set `service`."""

    _abstract = True
    service: ClassVar[str] = ""


class LLMProxyError(ExternalServiceError):
    """The university LiteLLM proxy (chat or embeddings) failed. Abstract."""

    _abstract = True
    service = "LiteLLM"


class ProxyUnreachableError(LLMProxyError):
    """Connection error or timeout, after the client's own retries."""


class ProxyAuthenticationError(LLMProxyError):
    """The proxy rejected the API key (HTTP 401/403)."""


class ModelNotAvailableError(LLMProxyError):
    """A configured model id is not offered by the proxy."""


class EmbeddingDimensionError(LLMProxyError):
    """The embedding length differs from EMBEDDING_DIMENSION."""


class VectorStoreError(ExternalServiceError):
    """Pinecone failed. Abstract."""

    _abstract = True
    service = "Pinecone"


class VectorStoreUnreachableError(VectorStoreError):
    """Pinecone could not be reached."""


class VectorStoreAuthenticationError(VectorStoreError):
    """Pinecone rejected the API key."""


class IndexNotFoundError(VectorStoreError):
    """The configured index does not exist."""


class IndexMismatchError(VectorStoreError):
    """The index exists with a different dimension or metric than Octi expects."""

    def __init__(self, expected: tuple[int, str], actual: tuple[int, str]) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"The Pinecone index has the wrong shape: expected {expected[0]} dimensions / {expected[1]}, "
            f"actual {actual[0]} dimensions / {actual[1]}."
        )


class TracingError(ExternalServiceError):
    """LangSmith failed. Abstract."""

    _abstract = True
    service = "LangSmith"


class TracingUnreachableError(TracingError):
    """LangSmith could not be reached."""


class TracingAuthenticationError(TracingError):
    """LangSmith rejected the API key."""
