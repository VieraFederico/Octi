"""The last four completed Analysis turns, built only from durable chat messages (FR-203)."""

from collections.abc import Sequence
from typing import Any

from agents.analyst.schemas import Turn


def build_window(messages: Sequence[dict[str, Any]]) -> list[Turn]:
    return [Turn(message["question"], message["content"]) for message in messages
            if message.get("kind") == "analysis" and message.get("status") == "finished"][-4:]
