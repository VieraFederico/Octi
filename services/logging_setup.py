"""Logging for the developer's terminal, with secret redaction (decision D-018).

Named `logging_setup` (not `logging`) so it does not shadow Python's standard `logging` module.

Redaction happens in the formatter, on the final text, so it also covers tracebacks and messages
built from `%s` arguments: any configured secret value is replaced with `***` before the line is
written (FR-009). `SecretStr` already masks secrets in `repr`; this is the safety net for library
messages that might echo a key.
"""

import logging
import sys
from typing import TextIO

from services.settings import MIN_SECRET_LENGTH, Settings

REDACTED = "***"
_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


class RedactingFormatter(logging.Formatter):
    """A formatter that removes known secret values from every formatted line."""

    def __init__(self, secrets: list[str]) -> None:
        super().__init__(_LOG_FORMAT)
        # Short values are never configured (FR-004a); the filter here is a second guard (BR-010).
        self._secrets = [secret for secret in secrets if len(secret) >= MIN_SECRET_LENGTH]

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        for secret in self._secrets:
            text = text.replace(secret, REDACTED)
        return text


class _OctiHandler(logging.StreamHandler):
    """Marker subclass so `configure_logging` can find and replace its own handler."""


def configure_logging(settings: Settings, stream: TextIO | None = None) -> None:
    """Set the root level from LOG_LEVEL and install one redacting stderr handler (idempotent)."""
    root = logging.getLogger()
    root.setLevel(settings.LOG_LEVEL)
    for handler in [h for h in root.handlers if isinstance(h, _OctiHandler)]:
        root.removeHandler(handler)
    handler = _OctiHandler(stream if stream is not None else sys.stderr)
    handler.setFormatter(RedactingFormatter(settings.secret_values()))
    root.addHandler(handler)
