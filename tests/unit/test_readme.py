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
