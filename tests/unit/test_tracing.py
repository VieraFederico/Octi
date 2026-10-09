"""LangSmith error translation (spec FR-008, BR-007)."""

import pytest
from langsmith.utils import LangSmithAuthError, LangSmithConnectionError, LangSmithRequestTimeout

from services.errors import TracingAuthenticationError, TracingUnreachableError
from services.tracing import translate_tracing_errors


@pytest.mark.parametrize(
    ("error", "leaf"),
    [
        (LangSmithAuthError("Authentication failed"), TracingAuthenticationError),
        (LangSmithConnectionError("Connection error"), TracingUnreachableError),
        (LangSmithRequestTimeout("Timed out"), TracingUnreachableError),
    ],
)
def test_langsmith_errors_become_tracing_leaves(error: Exception, leaf: type[Exception]) -> None:
    """FR-008: each LangSmith error becomes the matching leaf, original chained as `__cause__`."""
    # Given a block that raises a LangSmith error / When it runs inside the translator
    with pytest.raises(leaf) as caught, translate_tracing_errors():
        raise error
    # Then the leaf keeps the original as its cause, and its message is not the library's text
    assert caught.value.__cause__ is error
    assert str(error) not in caught.value.user_message
