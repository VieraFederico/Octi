"""Startup failure flow smoke tests: staged verification (D-118)."""

import pytest
import re
from html import unescape

from tests.stubs import FakeDockerClient


@pytest.mark.parametrize("reachable,image_present", [(False, True), (True, False)])
def test_unavailable_calculations_show_setup_instructions(start_app, monkeypatch, reachable, image_present) -> None:
    """VC-229 smoke: unavailable calculations show the setup instructions instead of the chat."""
    # Given
    client = FakeDockerClient(reachable=reachable, image_present=image_present)
    monkeypatch.setattr("services.sandbox.make_docker_client", lambda: client)

    # When
    app = start_app()

    # Then
    assert not app.exception
    html = " ".join(element.value for element in app.get("html"))
    assert "Docker" in html and "docker build -t octi-sandbox:1 sandbox/" in html
    text = " ".join(unescape(row).strip() for row in re.findall(r'<span class="octi-bubble-text">(.*?)</span>', html))
    assert "Getting started › Build the sandbox image" in text
    assert not app.chat_input and not app.sidebar.button
    assert client.closed
