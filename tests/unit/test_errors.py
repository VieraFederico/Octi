"""Error tree: groups for catching, leaves say exactly what happened (spec FR-007)."""

import pytest

from services import errors

# leaf -> (group it belongs to, service or None)
LEAVES = {
    errors.InvalidSettingsError: (errors.ConfigurationError, None),
    errors.ProxyUnreachableError: (errors.LLMProxyError, "LiteLLM"),
    errors.ProxyAuthenticationError: (errors.LLMProxyError, "LiteLLM"),
    errors.ModelNotAvailableError: (errors.LLMProxyError, "LiteLLM"),
    errors.EmbeddingDimensionError: (errors.LLMProxyError, "LiteLLM"),
    errors.VectorStoreUnreachableError: (errors.VectorStoreError, "Pinecone"),
    errors.VectorStoreAuthenticationError: (errors.VectorStoreError, "Pinecone"),
    errors.IndexMismatchError: (errors.VectorStoreError, "Pinecone"),
    errors.TracingUnreachableError: (errors.TracingError, "LangSmith"),
    errors.TracingAuthenticationError: (errors.TracingError, "LangSmith"),
    errors.SandboxUnavailableError: (errors.SandboxError, "Docker"),
    errors.DocumentUnreadableError: (errors.DocumentError, None),
    errors.DocumentEncryptedError: (errors.DocumentError, None),
    errors.DocumentWithoutTextError: (errors.DocumentError, None),
    errors.TableStoreError: (errors.AppError, None),
}

# Spec 01 FR-105 … FR-107: each document leaf always says its own sentence (D-059).
DOCUMENT_MESSAGES = {
    errors.DocumentUnreadableError: "I couldn't open this file. It may be damaged or not a real PDF.",
    errors.DocumentEncryptedError: "This PDF is password-protected. Remove the password and upload it again.",
    errors.DocumentWithoutTextError: (
        "This PDF has no selectable text (it looks scanned). I can only read PDFs with selectable text."
    ),
}


def build_leaf(leaf: type[errors.AppError]) -> errors.AppError:
    """Instantiate a leaf with representative arguments."""
    if leaf is errors.InvalidSettingsError:
        return leaf({"LLM_MODEL": "missing"})
    if leaf is errors.IndexMismatchError:
        return leaf(expected=(1536, "cosine"), actual=(3072, "cosine"))
    if issubclass(leaf, errors.DocumentError):
        return leaf()
    return leaf("Something specific went wrong.")


@pytest.mark.parametrize("leaf", list(LEAVES), ids=lambda cls: cls.__name__)
def test_leaves_have_group_message_and_service(leaf: type[errors.AppError]) -> None:
    """VC-011: each leaf belongs to its group, has a user message and (if external) names its service."""
    group, service = LEAVES[leaf]
    error = build_leaf(leaf)
    assert isinstance(error, group)
    assert error.user_message
    if service is None:
        assert not isinstance(error, errors.ExternalServiceError)
    else:
        assert error.service == service


def test_invalid_settings_exposes_field_names() -> None:
    """VC-011: InvalidSettingsError carries names and reasons, in order."""
    error = errors.InvalidSettingsError({"LITELLM_API_KEY": "missing", "LLM_MODEL": "missing"})
    assert error.fields == ("LITELLM_API_KEY", "LLM_MODEL")
    assert "LITELLM_API_KEY (missing)" in error.user_message


def test_index_mismatch_exposes_expected_and_actual() -> None:
    """VC-011: IndexMismatchError carries both sides and says them."""
    error = errors.IndexMismatchError(expected=(1536, "cosine"), actual=(3072, "dotproduct"))
    assert error.expected == (1536, "cosine")
    assert error.actual == (3072, "dotproduct")
    assert "expected 1536" in error.user_message and "actual 3072" in error.user_message


def test_leaf_can_chain_original_cause() -> None:
    """FR-008: a leaf raised `from` a library error keeps it as __cause__."""
    original = ConnectionError("socket closed")
    with pytest.raises(errors.ProxyUnreachableError) as caught:
        try:
            raise original
        except ConnectionError as exc:
            raise errors.ProxyUnreachableError("The LiteLLM proxy is unreachable.") from exc
    assert caught.value.__cause__ is original


@pytest.mark.parametrize("leaf", list(DOCUMENT_MESSAGES), ids=lambda cls: cls.__name__)
def test_document_leaves_say_their_spec_sentence(leaf: type[errors.DocumentError]) -> None:
    """VC-011 (spec 01 FR-105 … FR-107): a document leaf needs no argument and carries its exact sentence."""
    assert leaf().user_message == DOCUMENT_MESSAGES[leaf]


def test_table_store_error_sits_directly_under_app_error() -> None:
    """VC-011 (spec 01 §7 errors, D-080): the local disk is not an external service."""
    error = errors.TableStoreError("Couldn't save the table data on disk.")
    assert errors.TableStoreError.__bases__ == (errors.AppError,)
    assert not isinstance(error, errors.ExternalServiceError)
    assert error.user_message == "Couldn't save the table data on disk."


def test_sandbox_error_is_an_external_service_named_docker() -> None:
    """VC-238 (spec 02 §7 errors): SandboxError groups Docker failures under ExternalServiceError."""
    assert errors.SandboxError.__bases__ == (errors.ExternalServiceError,)
    assert errors.SandboxError.service == "Docker"
    assert errors.SandboxUnavailableError.__bases__ == (errors.SandboxError,)
