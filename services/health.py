"""Service check: one line per dependency, each `OK`, `FAIL` or `SKIPPED` with a safe reason.

Used by `scripts/check_services.py` and the live smoke test (FR-015 … FR-018, FR-035). The app does
not run it: it spends proxy budget, and Streamlit reruns often (D-025).

How to read this module:
- Each `check_*` function tells one story: build the client, make one call, return OK or raise a
  leaf error. It builds its own client, so a client that cannot be built fails only its own check.
- `run_checks` runs them in order and turns any exception into a `FAIL` line that shows only the
  leaf's `user_message` (BR-007). Text from library exceptions, which could echo a key or a raw proxy
  body, never reaches the output (BR-003).
- `Clients` says where each check gets its client. Tests pass stubs; production uses the defaults.

"Ask the proxy for its model list before the first call" adapted from the course's LiteLLM demo
notebook — see README › Credits.
"""

import logging
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Literal

from services.errors import AppError, EmbeddingDimensionError, InvalidSettingsError, ModelNotAvailableError
from services.llm import list_proxy_models, make_chat_model, make_embeddings, translate_proxy_errors
from services.settings import ENV_FILE, REPO_ROOT, Settings, get_settings
from services.tracing import make_langsmith_client, translate_tracing_errors
from services.vector_store import IndexClient, check_index, make_pinecone_client

logger = logging.getLogger(__name__)

CHAT_PROMPT = "Reply with the single word: OK"
EMBEDDING_PROBE = "Octi service check"
GIT_TIMEOUT_SECONDS = 10

# The checks that need valid configuration, in the order they are printed.
SERVICE_CHECKS = ("models", "chat", "embeddings", "pinecone", "langsmith")


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: Literal["OK", "FAIL", "SKIPPED"]
    reason: str = ""

    def line(self) -> str:
        """The line the script prints (FR-015, FR-016)."""
        if self.status == "OK":
            return f"{self.name}: OK"
        if self.status == "FAIL":
            return f"{self.name}: FAIL: {self.reason}"
        return f"{self.name}: skipped ({self.reason})"


# --- Where each check gets its client --------------------------------------------------------------


def run_git_in_repo(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run git from the repository root: fixed argument list, no shell, bounded time.

    Lives here, not in a service module: the git safety net is its only user.
    """
    return subprocess.run(args, cwd=REPO_ROOT, capture_output=True, text=True, timeout=GIT_TIMEOUT_SECONDS)


@dataclass(frozen=True)
class Clients:
    """One factory per service. Each check calls its factory itself, inside its own guarded step."""

    list_models: Callable[[Settings], Iterable[str]] = list_proxy_models
    chat_model: Callable[[Settings], Any] = make_chat_model
    embeddings: Callable[[Settings], Any] = make_embeddings
    pinecone: Callable[[Settings], IndexClient] = make_pinecone_client
    langsmith: Callable[[Settings], Any] = make_langsmith_client
    run_git: Callable[[list[str]], subprocess.CompletedProcess[str]] = run_git_in_repo


# --- The checks ----------------------------------------------------------------------------------


def check_models(settings: Settings, list_models: Callable[[Settings], Iterable[str]]) -> CheckResult:
    """The proxy offers both configured models. Catches a typo in LLM_MODEL / EMBEDDING_MODEL."""
    with translate_proxy_errors():
        available = set(list_models(settings))
    missing = [model for model in (settings.LLM_MODEL, settings.EMBEDDING_MODEL) if model not in available]
    if missing:
        raise ModelNotAvailableError(
            f"The proxy does not offer: {', '.join(missing)}. "
            "Compare LLM_MODEL / EMBEDDING_MODEL with the list sent on the course channel."
        )
    return CheckResult("models", "OK")


def check_chat(settings: Settings, make_chat: Callable[[Settings], Any]) -> CheckResult:
    """One minimal completion succeeds. The wording of the answer is not checked."""
    with translate_proxy_errors():
        make_chat(settings).invoke(CHAT_PROMPT)
    return CheckResult("chat", "OK")


def check_embeddings(settings: Settings, make_embedder: Callable[[Settings], Any]) -> CheckResult:
    """One embedding has exactly EMBEDDING_DIMENSION numbers."""
    with translate_proxy_errors():
        vector = make_embedder(settings).embed_query(EMBEDDING_PROBE)
    if len(vector) != settings.EMBEDDING_DIMENSION:
        raise EmbeddingDimensionError(
            f"The embedding model returns vectors of {len(vector)} numbers; expected "
            f"{settings.EMBEDDING_DIMENSION} (EMBEDDING_DIMENSION and the Pinecone index must match the model)."
        )
    return CheckResult("embeddings", "OK")


def check_pinecone(settings: Settings, make_client: Callable[[Settings], IndexClient]) -> CheckResult:
    """The index exists with the expected dimension and metric (read-only, through `check_index`)."""
    status = check_index(settings, make_client(settings))
    if status.outcome == "ok":
        return CheckResult("pinecone", "OK")
    return CheckResult("pinecone", "FAIL", status.reason)


def check_langsmith(settings: Settings, make_client: Callable[[Settings], Any]) -> CheckResult:
    """Tracing is on, and an authenticated LangSmith request succeeds (D-024: tracing off is a FAIL)."""
    if not settings.LANGSMITH_TRACING:
        return CheckResult(
            "langsmith", "FAIL", "tracing is off. Set LANGSMITH_TRACING=true: the assignment requires every run traced."
        )
    with translate_tracing_errors():
        # `list_projects` is lazy: asking for the first item is what sends the authenticated request.
        next(iter(make_client(settings).list_projects(limit=1)), None)
    return CheckResult("langsmith", "OK")


def check_git_tracking(run_git: Callable[[list[str]], subprocess.CompletedProcess[str]]) -> CheckResult:
    """Safety net (FR-016): the secrets file must not be tracked by git.

    Only asks git whether the file name is in its index; the file itself is never opened.
    """
    name = ENV_FILE.name
    try:
        answer = run_git(["git", "ls-files", "--error-unmatch", "--", name])
    except FileNotFoundError:
        return CheckResult("git", "SKIPPED", "git is not installed")
    except subprocess.TimeoutExpired:
        return CheckResult("git", "SKIPPED", "git did not answer")

    if answer.returncode == 0:  # git knows the file: it is tracked
        return CheckResult(
            "git", "FAIL", f"{name} is tracked by git. Untrack it with: git rm --cached {name} (keep it in .gitignore)"
        )
    if "not a git repository" in answer.stderr.lower():
        return CheckResult("git", "SKIPPED", "not a git repository")
    if answer.returncode == 1:  # "did not match any file known to git": not tracked
        return CheckResult("git", "OK")
    return CheckResult("git", "SKIPPED", "git could not answer")


# --- Running them all ----------------------------------------------------------------------------


def run_checks(load_settings: Callable[[], Settings] = get_settings, clients: Clients = Clients()) -> list[CheckResult]:
    """Run every check in order, even after failures (FR-017); skip service checks without configuration (FR-018)."""
    try:
        settings = load_settings()
    except InvalidSettingsError as exc:
        results = [CheckResult("configuration", "FAIL", exc.user_message)]
        results += [CheckResult(name, "SKIPPED", "configuration is invalid") for name in SERVICE_CHECKS]
    else:
        results = [
            CheckResult("configuration", "OK"),
            _safely("models", lambda: check_models(settings, clients.list_models)),
            _safely("chat", lambda: check_chat(settings, clients.chat_model)),
            _safely("embeddings", lambda: check_embeddings(settings, clients.embeddings)),
            _safely("pinecone", lambda: check_pinecone(settings, clients.pinecone)),
            _safely("langsmith", lambda: check_langsmith(settings, clients.langsmith)),
        ]
    results.append(_safely("git", lambda: check_git_tracking(clients.run_git)))
    return results


def _safely(name: str, check: Callable[[], CheckResult]) -> CheckResult:
    """Run one check; any exception becomes a FAIL line with a safe reason."""
    try:
        return check()
    except AppError as exc:
        return CheckResult(name, "FAIL", exc.user_message)
    except Exception as exc:  # not ours: its text may hold secrets, so show only the class name
        logger.debug("Unexpected error in the %s check", name, exc_info=True)
        return CheckResult(name, "FAIL", f"unexpected {type(exc).__name__}. Run again with LOG_LEVEL=DEBUG for details.")
