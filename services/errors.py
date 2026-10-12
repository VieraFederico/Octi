"""Octi's error tree (decision D-027).

Group classes let callers write `except VectorStoreError`; code raises a *leaf* that names exactly
what happened and carries a `user_message` that is safe to show in the UI. The original library
exception is chained with `raise Leaf(...) from exc`, so logs keep the details while the UI never
shows them.

    AppError
    ├── ConfigurationError
    │   └── InvalidSettingsError
    ├── DocumentError                   (the uploaded file cannot be ingested at all)
    │   ├── DocumentUnreadableError
    │   ├── DocumentEncryptedError
    │   └── DocumentWithoutTextError
    ├── TableStoreError                 (local disk: reading or writing a Table's data file)
    └── ExternalServiceError            (.service)
        ├── LLMProxyError               (LiteLLM: chat + embeddings)
        │   ├── ProxyUnreachableError
        │   ├── ProxyAuthenticationError
        │   ├── ModelNotAvailableError
        │   └── EmbeddingDimensionError
        ├── VectorStoreError            (Pinecone)
        │   ├── VectorStoreUnreachableError
        │   ├── VectorStoreAuthenticationError
        │   └── IndexMismatchError
        ├── TracingError                (LangSmith)
        │   ├── TracingUnreachableError
        │   └── TracingAuthenticationError
        └── SandboxError                (Docker: the sandbox that runs generated code)
            └── SandboxUnavailableError

Rule (BR-011): add a new leaf only when code or UI must react differently, or the user message differs.
"""

from collections.abc import Mapping
from typing import ClassVar


class AppError(Exception):
    """Root of every error Octi raises on purpose."""

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


# --- Configuration -----------------------------------------------------------------------------


class ConfigurationError(AppError):
    """Octi's own configuration is wrong."""


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


# --- Documents (spec 01) -----------------------------------------------------------------------


class DocumentError(AppError):
    """The uploaded file cannot be ingested at all (spec 01 FR-105 … FR-107).

    Each leaf always says the same sentence, so it is a class attribute and the leaf takes no
    argument: `raise DocumentEncryptedError()`.
    """

    message: ClassVar[str] = ""

    def __init__(self) -> None:
        super().__init__(self.message)


class DocumentUnreadableError(DocumentError):
    """PyMuPDF cannot open the bytes, or they are not a PDF (FR-105)."""

    message = "I couldn't open this file. It may be damaged or not a real PDF."


class DocumentEncryptedError(DocumentError):
    """The PDF needs a password to be opened (FR-106)."""

    message = "This PDF is password-protected. Remove the password and upload it again."


class DocumentWithoutTextError(DocumentError):
    """No page of the PDF has selectable text, e.g. a scan (FR-107)."""

    message = "This PDF has no selectable text (it looks scanned). I can only read PDFs with selectable text."


# --- Table store (spec 01) ---------------------------------------------------------------------


class TableStoreError(AppError):
    """Reading or writing a Table's data file on the local disk failed (spec 01 FR-139).

    Directly under `AppError`: the disk is not an external service (D-080).
    """


# --- External services -------------------------------------------------------------------------


class ExternalServiceError(AppError):
    """A service Octi depends on failed. `service` names it."""

    service: ClassVar[str] = ""


class LLMProxyError(ExternalServiceError):
    """The university LiteLLM proxy (chat or embeddings) failed."""

    service = "LiteLLM"


class ProxyUnreachableError(LLMProxyError):
    """Connection error, timeout or server error, after the client's own retries."""


class ProxyAuthenticationError(LLMProxyError):
    """The proxy rejected the API key (HTTP 401/403)."""


class ModelNotAvailableError(LLMProxyError):
    """A configured model id is not offered by the proxy."""


class EmbeddingDimensionError(LLMProxyError):
    """The embedding length differs from EMBEDDING_DIMENSION."""


class VectorStoreError(ExternalServiceError):
    """Pinecone failed."""

    service = "Pinecone"


class VectorStoreUnreachableError(VectorStoreError):
    """Pinecone could not be reached, or did not answer in time."""


class VectorStoreAuthenticationError(VectorStoreError):
    """Pinecone rejected the API key."""


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
    """LangSmith failed."""

    service = "LangSmith"


class TracingUnreachableError(TracingError):
    """LangSmith could not be reached."""


class TracingAuthenticationError(TracingError):
    """LangSmith rejected the API key."""


class SandboxError(ExternalServiceError):
    """The local Docker daemon or the sandbox image failed (spec 02).

    A timeout or a failing script is an attempt outcome, not an error.
    """

    service = "Docker"


class SandboxUnavailableError(SandboxError):
    """The Docker daemon is unreachable or the image `octi-sandbox:1` is missing (spec 02 FR-231, FR-232)."""
