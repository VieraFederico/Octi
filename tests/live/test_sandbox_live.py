"""Student-run isolation checks, using harmless canaries and the existing local image."""

from pathlib import Path

import pytest

from services.sandbox import prepare_run_folder, run_script

pytestmark = pytest.mark.live


def test_normal_script_succeeds(tmp_path: Path) -> None:
    """VC-245: a normal calculation completes and its owned folder is removed."""
    folder = prepare_run_folder("print(6 * 7)", {}, base_dir=tmp_path)
    result = run_script(folder, 5)
    assert result.exit_code == 0 and not result.timed_out
    assert result.stdout.strip() == "42"
    assert not folder.exists()


def test_host_file_outside_mount_is_inaccessible(tmp_path: Path) -> None:
    """VC-245: an absolute host path is inaccessible; no actual secret file is touched."""
    canary = tmp_path / "host-only-canary.txt"
    canary.write_text("harmless-isolation-canary", encoding="utf-8")
    script = f"from pathlib import Path\nprint(Path({str(canary.resolve())!r}).read_text())"
    result = run_script(prepare_run_folder(script, {}, base_dir=tmp_path), 5)
    assert result.exit_code != 0 and not result.timed_out
    assert "harmless-isolation-canary" not in result.stdout
    assert "FileNotFoundError" in result.stderr


def test_network_call_is_blocked(tmp_path: Path) -> None:
    """VC-245: a direct connection cannot escape the container's disabled network."""
    script = "import socket\nsocket.create_connection(('1.1.1.1', 443), timeout=2)\nprint('connected')"
    result = run_script(prepare_run_folder(script, {}, base_dir=tmp_path), 5)
    assert result.exit_code != 0 and not result.timed_out
    assert "connected" not in result.stdout


def test_endless_loop_is_killed(tmp_path: Path) -> None:
    """VC-245: the wall-clock deadline kills runaway generated code."""
    result = run_script(prepare_run_folder("while True:\n    pass", {}, base_dir=tmp_path), 5)
    assert result.timed_out and result.exit_code != 0


def test_fork_bomb_hits_process_limit(tmp_path: Path) -> None:
    """VC-245: forking stops at the configured process limit, before the deadline."""
    script = """import os
import time
children = []
try:
    while True:
        pid = os.fork()
        if pid == 0:
            time.sleep(30)
            os._exit(0)
        children.append(pid)
except OSError as error:
    print('process-limit', error.errno, flush=True)
finally:
    for pid in children:
        os.kill(pid, 9)
    for pid in children:
        os.waitpid(pid, 0)
"""
    result = run_script(prepare_run_folder(script, {}, base_dir=tmp_path), 5)
    assert not result.timed_out and result.exit_code == 0
    assert "process-limit 11" in result.stdout
