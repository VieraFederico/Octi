"""Sandbox smoke tests with a fake client: staged verification (D-118)."""

import stat

from services.sandbox import OUTPUT_CAP_BYTES, prepare_run_folder, run_script
from tests.stubs import FakeDockerClient


def test_calculation_runs_with_isolation_and_releases_its_files(tmp_path) -> None:
    """VC-215/216/218 smoke: a calculation retains its final output and cleans up its inputs."""
    # Given
    table = tmp_path / "selected.parquet"
    table.write_bytes(b"selected table fixture")
    script = "# trusted prelude followed by generated code\n"
    folder = prepare_run_folder(script, {"selected": table}, base_dir=tmp_path)
    assert sorted(path.name for path in folder.iterdir()) == ["main.py", "selected.parquet"]
    assert (folder / "main.py").read_text(encoding="utf-8") == script
    assert (folder / "selected.parquet").read_bytes() == table.read_bytes()
    assert stat.S_IMODE(folder.stat().st_mode) == 0o755
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o644 for path in folder.iterdir())
    final_line = b'\n{"parts": []}\n'
    client = FakeDockerClient(stdout=b"x" * (1024 * 1024) + final_line)

    # When
    result = run_script(folder, 30, client=client)

    # Then
    assert result.exit_code == 0 and not result.timed_out
    assert result.stdout.endswith(final_line.decode())
    assert len(result.stdout.encode()) == OUTPUT_CAP_BYTES
    assert client.create_calls == [{
        "image": "octi-sandbox:1", "command": ["python", "/work/main.py"],
        "network_disabled": True, "read_only": True,
        "tmpfs": {"/tmp": "size=64m"}, "mem_limit": "512m", "memswap_limit": "512m",
        "nano_cpus": 1_000_000_000, "pids_limit": 64, "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges"], "user": "10001", "environment": {},
        "volumes": {str(folder): {"bind": "/work", "mode": "ro"}},
    }]
    assert client.container.started and client.container.removed
    assert not client.container.killed and not folder.exists()
    assert table.exists() and not client.closed  # the caller owns an injected client


def test_timeout_kills_the_calculation_and_releases_its_files(tmp_path) -> None:
    """VC-217 smoke: an expired calculation is killed and its isolated files are removed."""
    # Given
    folder = prepare_run_folder("while True: pass\n", {}, base_dir=tmp_path)
    client = FakeDockerClient(timed_out=True, stderr=b"before timeout")

    # When
    result = run_script(folder, 5, client=client)

    # Then
    assert result.timed_out and result.exit_code != 0
    assert result.stderr == "before timeout"
    assert client.container.wait_timeouts == [5]
    assert client.container.killed and client.container.removed
    assert not folder.exists()
