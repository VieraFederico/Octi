"""Logging: configurable level and secret redaction (spec FR-009, FR-010, BR-010)."""

import io
import logging

import pytest

from services.logging_setup import configure_logging
from tests.conftest import FAKE_LITELLM_KEY, FAKE_PINECONE_KEY


@pytest.fixture(autouse=True)
def restore_root_logger():
    """Each test leaves the root logger as it found it."""
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)


def test_secret_in_log_line_is_redacted(make_settings) -> None:
    """VC-013: a configured secret never reaches the log output."""
    stream = io.StringIO()
    configure_logging(make_settings(), stream=stream)
    logging.getLogger("octi.test").warning("calling proxy with key %s", FAKE_LITELLM_KEY)
    output = stream.getvalue()
    assert "***" in output
    assert FAKE_LITELLM_KEY not in output


def test_secret_inside_traceback_is_redacted(make_settings) -> None:
    """VC-013: redaction also covers exception text written by the formatter."""
    stream = io.StringIO()
    configure_logging(make_settings(), stream=stream)
    try:
        raise RuntimeError(f"auth failed for {FAKE_PINECONE_KEY}")
    except RuntimeError:
        logging.getLogger("octi.test").exception("pinecone call failed")
    assert FAKE_PINECONE_KEY not in stream.getvalue()


def test_ordinary_words_are_left_intact(make_settings) -> None:
    """VC-013a: only long secrets are replaced, so normal prose survives."""
    stream = io.StringIO()
    configure_logging(make_settings(), stream=stream)
    logging.getLogger("octi.test").warning("leveraging the index")
    assert "leveraging the index" in stream.getvalue()


def test_log_level_comes_from_settings(make_settings) -> None:
    """VC-014: LOG_LEVEL=DEBUG sets DEBUG; unset defaults to INFO."""
    configure_logging(make_settings(LOG_LEVEL="DEBUG"), stream=io.StringIO())
    assert logging.getLogger().level == logging.DEBUG
    configure_logging(make_settings(), stream=io.StringIO())
    assert logging.getLogger().level == logging.INFO


def test_configuring_twice_does_not_duplicate_output(make_settings) -> None:
    """Calling configure_logging again (e.g. a Streamlit rerun) keeps one Octi handler."""
    stream = io.StringIO()
    configure_logging(make_settings(), stream=stream)
    configure_logging(make_settings(), stream=stream)
    logging.getLogger("octi.test").warning("once")
    assert stream.getvalue().count("once") == 1
