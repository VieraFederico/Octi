"""Sandbox diagnostic smoke tests: staged verification (D-118)."""

from dataclasses import replace

import pytest

from scripts.check_services import main
from tests.analyst_stubs import FakeDockerClient
from tests.stubs import healthy_clients


@pytest.mark.parametrize("image_present", [True, False])
def test_service_report_includes_sandbox_and_keeps_other_checks(make_settings, capsys, image_present) -> None:
    """VC-230 smoke: the diagnostic report includes the calculation service and every other check."""
    # Given
    client = FakeDockerClient(image_present=image_present)
    clients = replace(healthy_clients(), docker=lambda: client)

    # When
    exit_code = main(lambda: make_settings(LANGSMITH_TRACING="true"), clients)

    # Then
    lines = capsys.readouterr().out.splitlines()
    docker_line = next(line for line in lines if line.startswith("docker:"))
    assert docker_line.startswith("docker: OK" if image_present else "docker: FAIL:")
    assert exit_code == (0 if image_present else 1)
    assert "chat: OK" in lines and "langsmith: OK" in lines and "git: OK" in lines
    assert client.closed
