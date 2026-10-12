"""The README is the setup document (spec FR-036, VC-042, NFR-004, decisions D-017, D-023, D-026)."""

import re

from services.settings import REPO_ROOT

README = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

# D-023's order: purpose, then the setup steps a new reader follows top to bottom.
SETUP_HEADINGS = [
    "Getting started",
    "Prerequisites",
    "Create a virtual environment and install the dependencies",
    "Configure your secrets",
    "Create the Pinecone index",
    "Check every service",
    "Run the tests",
    "Run the app",
]


def headings() -> list[str]:
    """Every Markdown heading's text, without the leading #'s or a step number like "1. "."""
    return [re.sub(r"^\d+\.\s*", "", match) for match in re.findall(r"^#{1,6}\s+(.+?)\s*$", README, flags=re.MULTILINE)]


def test_purpose_comes_before_the_setup() -> None:
    """VC-042: the README opens with what Octi is, before any setup step."""
    purpose = README.split("## Getting started")[0]
    assert "Octi answers questions" in purpose


def test_setup_sections_are_in_order() -> None:
    """VC-042: prerequisites, venv + install, .env, index setup, service check, tests, the app."""
    found = headings()
    positions = [found.index(heading) for heading in SETUP_HEADINGS]  # ValueError names a missing heading
    assert positions == sorted(positions)


def test_secrets_step_has_the_security_notes() -> None:
    """FR-036 (D-017): the reader learns the secrets file is already in `.gitignore`, and `chmod 600` is advised."""
    secrets = README.split("Configure your secrets")[1].split("Create the Pinecone index")[0]
    assert ".env.example" in secrets
    assert ".gitignore" in secrets
    assert "chmod 600" in secrets


def test_retries_are_explained_against_the_course_labs() -> None:
    """FR-036 (D-026): client retries are the OpenAI client's built-in ones, unlike the course labs."""
    assert "built-in" in README
    assert "max_retries=0" in README


def test_credits_is_the_last_section() -> None:
    """Assignment §11: credits for every course source, at the end."""
    assert [line for line in README.splitlines() if line.startswith("## ")][-1] == "## Credits"


def test_readme_does_not_point_into_the_build_notes() -> None:
    """The README is for a reader who was not here: no links into specs, plans or local course files."""
    for internal in ("specs/", "plan-artifacts", "sources/"):
        assert internal not in README


def test_every_requirement_is_pinned() -> None:
    """VC-042 (NFR-004): every dependency line in requirements.txt uses ==."""
    lines = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    dependencies = [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]
    assert dependencies
    assert [line for line in dependencies if "==" not in line] == []


def test_ingestion_documentation_and_exported_graph_are_present(make_settings) -> None:
    """VC-162: ingestion setup, storage, graph and limitations are documented for users."""
    # Given / When
    text = README
    # Then
    for phrase in ("INGESTION_MAX_RETRIES", "AGPL-3.0", "Parquet", "38 KB", "fetch_by_metadata",
                   "python -m scripts.make_sample_pdfs", "## Known limitations", "```mermaid"):
        assert phrase in text
    graph = text.split("```mermaid", 1)[1].split("```", 1)[0]
    for node in ("load_pdf", "extract_tables", "ask_unreadable", "collect_context", "enrich",
                 "validate", "next_table", "ask_skipped", "index"):
        assert node in graph
    from agents.ingestion.graph import build_graph
    from agents.ingestion.state import IngestionDeps
    from tests.stubs import FakeEmbeddings, FakePineconeIndex
    exported = build_graph(IngestionDeps(make_settings(), FakeEmbeddings(), FakePineconeIndex())).get_graph().draw_mermaid()
    assert graph.strip() == exported.strip()
    for limitation in ("borderless", "numeric headers", "headerless", "1.234", "English", "scanned"):
        assert limitation.lower() in " ".join(text.lower().split())


def test_ingestion_status_and_usage_describe_the_shipped_ui() -> None:
    """VC-162: the reader learns how uploads, confirmations, pauses and the Library work."""
    # Given / When
    text = README
    # Then
    assert "The two agents are\nnot built yet" not in text
    for phrase in ("Open in library", "Cancel ingestion", "Replace", "Keep", "Show more", "View all"):
        assert phrase in text


def test_analyst_documentation_and_exported_graph_are_present(make_settings) -> None:
    """VC-242/243: setup, calculation choices and the actual Analyst graph are documented."""
    from agents.analyst.graph import NODE_NAMES, build_graph
    from agents.analyst.state import make_deps

    for phrase in ("### Analyst", "ANALYST_MAX_RETRIES", "SANDBOX_TIMEOUT_SECONDS",
                   "docker build -t octi-sandbox:1 sandbox/", "512 MB", "64 processes",
                   "four completed", "number check", "wrong row", "wrong entity"):
        assert phrase in README
    blocks = re.findall(r"```mermaid\s*\n(.*?)```", README, flags=re.DOTALL)
    exported = build_graph(make_deps(make_settings())).get_graph().draw_mermaid()
    assert exported.strip() in [block.strip() for block in blocks]
    assert all(node in exported for node in NODE_NAMES)
    dockerfile = (REPO_ROOT / "sandbox" / "Dockerfile").read_text(encoding="utf-8")
    for phrase in ("python:3.13-slim", "pandas==3.0.6", "pyarrow==25.0.1", "10001"):
        assert phrase in dockerfile
