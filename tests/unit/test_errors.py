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
}


def build_leaf(leaf: type[errors.AppError]) -> errors.AppError:
    """Instantiate a leaf with representative arguments."""
    if leaf is errors.InvalidSettingsError:
        return leaf({"LLM_MODEL": "missing"})
    if leaf is errors.IndexMismatchError:
        return leaf(expected=(1536, "cosine"), actual=(3072, "cosine"))
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
