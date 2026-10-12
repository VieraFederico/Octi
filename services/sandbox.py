"""Run a folder's script in an isolated container (spec 02, D-085/D-086).

This module handles execution only. The caller supplies the complete script and selected files;
the Analyst builds its prelude and interprets the result. No host configuration is sent inside.
The SDK is loaded only when building a real client, so offline fakes need no Docker installation.
"""

import logging
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from requests.exceptions import ReadTimeout, RequestException

from services.errors import SandboxUnavailableError

logger = logging.getLogger(__name__)

SANDBOX_IMAGE = "octi-sandbox:1"
BUILD_COMMAND = "docker build -t octi-sandbox:1 sandbox/"
WORK_DIR = "/work"
OUTPUT_CAP_BYTES = 64 * 1024
RUN_FOLDER_PREFIX = "octi-sandbox-"
FALLBACK_RUN_DIR = Path(__file__).resolve().parent.parent / "data" / "sandbox_runs"
CLIENT_TIMEOUT_SECONDS = 10
UNAVAILABLE_MESSAGE = "The calculation service is unavailable. Please try again in a moment."


class Container(Protocol):
    def start(self) -> None: ...
    def wait(self, *, timeout: int) -> dict[str, Any]: ...
    def kill(self) -> None: ...
    def logs(self, *, stdout: bool, stderr: bool, stream: bool, follow: bool) -> Iterator[bytes]: ...
    def remove(self, *, force: bool) -> None: ...


class Containers(Protocol):
    def create(self, *, image: str, command: list[str], **kwargs: Any) -> Container: ...


class Images(Protocol):
    def get(self, name: str) -> Any: ...


class DockerClient(Protocol):
    containers: Containers
    images: Images

    def ping(self) -> bool: ...
    def close(self) -> None: ...


@dataclass(frozen=True)
class SandboxResult:
    exit_code: int
    timed_out: bool
    stdout: str
    stderr: str


@dataclass(frozen=True)
class DockerStatus:
    outcome: Literal["ok", "unreachable", "image_missing"]

    @property
    def reason(self) -> str:
        """Fixed developer-facing advice; never library exception text."""
        if self.outcome == "image_missing":
            return f"Docker cannot find {SANDBOX_IMAGE}. Build it with: {BUILD_COMMAND}"
        if self.outcome == "unreachable":
            return "Docker is unavailable. Check its Python SDK and start Docker, then restart the app."
        return ""


def _service_errors() -> tuple[type[Exception], ...]:
    """SDK exceptions when present, plus its transport errors and local file errors."""
    try:
        from docker.errors import DockerException
    except ImportError:
        return (RequestException, OSError, ImportError)
    return (DockerException, RequestException, OSError, ImportError)


@contextmanager
def translate_sandbox_errors() -> Iterator[None]:
    """Translate service/disk failures into a safe leaf error, chaining the original cause."""
    try:
        yield
    except _service_errors() as exc:
        logger.debug("Sandbox operation failed", exc_info=True)
        raise SandboxUnavailableError(UNAVAILABLE_MESSAGE) from exc


def make_docker_client() -> DockerClient:
    """Build the SDK client on the host; its connection configuration never enters a container."""
    with translate_sandbox_errors():
        import docker

        return docker.from_env(timeout=CLIENT_TIMEOUT_SECONDS)


def prepare_run_folder(
    script: str, table_files: dict[str, Path], *, base_dir: Path | None = None,
) -> Path:
    """Copy only `main.py` and the given tables into a new owned folder (0755/files 0644).

    `base_dir=None` uses system temporary storage; pass `FALLBACK_RUN_DIR` if the daemon cannot
    mount that storage. This service does not choose tables or add an Analyst prelude.
    """
    for table_id in table_files:
        if not table_id or table_id in (".", "..") or "/" in table_id or "\\" in table_id:
            raise ValueError("A table id must be a file name.")
    folder = None
    with translate_sandbox_errors():
        try:
            if base_dir is not None:
                base_dir.mkdir(parents=True, exist_ok=True)
            folder = Path(tempfile.mkdtemp(prefix=RUN_FOLDER_PREFIX, dir=base_dir)).resolve()
            folder.chmod(0o755)
            main = folder / "main.py"
            main.write_text(script, encoding="utf-8")
            main.chmod(0o644)
            for table_id, source in table_files.items():
                target = folder / f"{table_id}.parquet"
                shutil.copyfile(source, target)
                target.chmod(0o644)
            return folder
        except Exception:
            if folder is not None:
                _remove_run_folder(folder)
            raise


def _remove_run_folder(folder: Path) -> None:
    """Remove only the named temporary run folder, never its parent or a symlink target."""
    parent = folder.parent.resolve()
    resolved = folder.resolve()
    if folder.is_symlink() or resolved.parent != parent or not resolved.name.startswith(RUN_FOLDER_PREFIX):
        raise ValueError("Cleanup requires an owned sandbox run folder.")
    if resolved.exists():
        shutil.rmtree(resolved)


def _output(container: Container, *, stdout: bool) -> str:
    """Retain the last 64 KB without accumulating the whole stream in application memory."""
    data = bytearray()
    chunks = container.logs(stdout=stdout, stderr=not stdout, stream=True, follow=False)
    try:
        for chunk in chunks:
            data.extend(chunk[-OUTPUT_CAP_BYTES:])
            if len(data) > OUTPUT_CAP_BYTES:
                del data[:-OUTPUT_CAP_BYTES]
    finally:
        close = getattr(chunks, "close", None)
        if close is not None:
            close()
    return data.decode("utf-8", errors="ignore")


def run_script(folder: Path, timeout_s: int, client: DockerClient | None = None) -> SandboxResult:
    """Run an owned folder from `prepare_run_folder`; always attempt container/folder cleanup.

    Timeout and nonzero exits are attempt results. Missing SDK/image/daemon and disk failures
    raise `SandboxUnavailableError`. Injected clients remain owned by the caller.
    """
    folder = Path(folder).absolute()
    if folder.is_symlink() or not folder.name.startswith(RUN_FOLDER_PREFIX):
        raise ValueError("Execution requires an owned sandbox run folder.")
    folder = folder.resolve()
    container = None
    owned_client = client is None
    with translate_sandbox_errors():
        try:
            client = client if client is not None else make_docker_client()
            client.images.get(SANDBOX_IMAGE)  # local lookup only; never pull a missing image
            container = client.containers.create(
                image=SANDBOX_IMAGE, command=["python", f"{WORK_DIR}/main.py"],
                network_disabled=True, read_only=True, tmpfs={"/tmp": "size=64m"},
                mem_limit="512m", memswap_limit="512m", nano_cpus=1_000_000_000,
                pids_limit=64, cap_drop=["ALL"], security_opt=["no-new-privileges"],
                user="10001", environment={},
                volumes={str(folder): {"bind": WORK_DIR, "mode": "ro"}},
            )
            container.start()
            timed_out = False
            try:
                exit_code = container.wait(timeout=timeout_s)["StatusCode"]
            except (ReadTimeout, TimeoutError):
                timed_out = True
                container.kill()
                exit_code = 137  # SIGKILL; the timed_out flag controls attempt classification
            return SandboxResult(exit_code, timed_out, _output(container, stdout=True), _output(container, stdout=False))
        finally:
            try:
                if container is not None:
                    container.remove(force=True)
            finally:
                try:
                    _remove_run_folder(folder)
                finally:
                    if owned_client and client is not None:
                        client.close()


def check_docker(client: DockerClient | None = None) -> DockerStatus:
    """Cheap read-only startup check: ping, then local image lookup; never build or pull."""
    owned_client = client is None
    outcome: Literal["ok", "unreachable", "image_missing"] = "unreachable"
    try:
        with translate_sandbox_errors():
            client = client if client is not None else make_docker_client()
            if client.ping():
                try:
                    client.images.get(SANDBOX_IMAGE)
                except _service_errors() as exc:
                    logger.debug("Sandbox image lookup failed", exc_info=True)
                    if getattr(getattr(exc, "response", None), "status_code", None) == 404:
                        outcome = "image_missing"
                    else:
                        raise
                else:
                    outcome = "ok"
    except SandboxUnavailableError:
        outcome = "unreachable"
    finally:
        if owned_client and client is not None:
            try:
                with translate_sandbox_errors():
                    client.close()
            except SandboxUnavailableError:
                outcome = "unreachable"
    return DockerStatus(outcome)
