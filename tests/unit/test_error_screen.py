"""The Octi error screen: what it says and which frames it plays (spec FR-027 … FR-028, D-031, D-032)."""

from pathlib import Path

import pytest

from services.errors import InvalidSettingsError
from services.settings import REPO_ROOT
from tests.stubs import FAKE_PINECONE_KEY, MISMATCH_INDEX, MISSING_INDEX, OK_INDEX, UNREACHABLE_INDEX
from ui.error_screen import CONFIG_SECTION, INDEX_SECTION, SERVICES_SECTION, error_frames, error_message, error_screen_html
from ui.startup import Startup


def write_frames(folder: Path, *texts: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for number, text in enumerate(texts, start=1):
        (folder / f"frame_{number:02d}.txt").write_text(text, encoding="utf-8")
    return folder


# --- Start-up result ------------------------------------------------------------------------------


def test_startup_is_ok_only_with_settings_and_a_ready_index(make_settings) -> None:
    """The shell opens only when configuration parsed and the index is `ok` (D-031)."""
    settings = make_settings()
    assert Startup(settings, OK_INDEX).ok
    assert not Startup(settings, MISSING_INDEX).ok
    assert not Startup(None, None, InvalidSettingsError({"LITELLM_API_KEY": "missing"})).ok


# --- Messages -----------------------------------------------------------------------------------


def test_invalid_configuration_names_the_variable_and_how_to_fix_it() -> None:
    """VC-032: the variable name, the `.env.example` instruction, a restart, and the README section."""
    message = error_message(Startup(None, None, InvalidSettingsError({"LITELLM_API_KEY": "missing"})))
    assert "LITELLM_API_KEY" in message
    assert ".env.example" in message
    assert "restart" in message
    assert f"README › {CONFIG_SECTION}" in message


def test_missing_index_gives_the_setup_command(make_settings) -> None:
    """VC-033: `missing` → the index name and the setup command."""
    message = error_message(Startup(make_settings(), MISSING_INDEX))
    assert "'octi-tables' does not exist" in message
    assert "python -m scripts.setup_index" in message
    assert f"README › {INDEX_SECTION}" in message


def test_mismatched_index_shows_expected_and_actual_shape(make_settings) -> None:
    """VC-033: `mismatch` → expected vs actual dimension and metric, and how to fix it."""
    message = error_message(Startup(make_settings(), MISMATCH_INDEX))
    assert "1536 dimensions / cosine" in message
    assert "3072 dimensions / dotproduct" in message
    assert "PINECONE_INDEX_NAME" in message
    assert "python -m scripts.setup_index" in message
    assert f"README › {INDEX_SECTION}" in message


def test_unreachable_index_points_at_the_network_and_the_key(make_settings) -> None:
    """VC-033: `unreachable` → check the connection and PINECONE_API_KEY; run the service check."""
    message = error_message(Startup(make_settings(), UNREACHABLE_INDEX))
    assert "connection" in message
    assert "PINECONE_API_KEY" in message
    assert "python -m scripts.check_services" in message
    assert f"README › {SERVICES_SECTION}" in message


@pytest.mark.parametrize("status", [MISSING_INDEX, MISMATCH_INDEX, UNREACHABLE_INDEX])
def test_the_screen_never_echoes_the_index_reason(make_settings, status) -> None:
    """VC-033a (BR-007): messages are built from the status fields, never from its `reason` text, so a
    reason carrying a key cannot reach the screen."""
    html = error_screen_html(error_message(Startup(make_settings(), status)), frames=[])
    assert status.reason not in html
    assert FAKE_PINECONE_KEY not in html


def test_every_readme_section_named_on_the_screen_exists() -> None:
    """The README sections the bubble points to must exist, or the advice leads nowhere."""
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    for section in (CONFIG_SECTION, INDEX_SECTION, SERVICES_SECTION):
        assert section.split(" › ")[-1] in readme


# --- Screen -------------------------------------------------------------------------------------


def test_screen_holds_octi_then_the_bubble() -> None:
    """FR-027a: Octi first (left, or above on a narrow screen), then the bubble with the message."""
    html = error_screen_html("Something failed.", frames=["octi"])
    assert html.index("octi-logo") < html.index("octi-bubble") < html.index("Something failed.")
    assert 'class="octi-error"' in html


def test_error_frames_are_played_when_present(tmp_path: Path) -> None:
    """VC-033b: frames in the error folder → those are played."""
    error_dir = write_frames(tmp_path / "error", "worried")
    main_dir = write_frames(tmp_path / "main", "happy")
    assert error_frames(error_dir, main_dir) == ["worried"]


def test_main_frames_are_played_when_the_error_folder_is_empty(tmp_path: Path) -> None:
    """VC-033b: empty (or missing) error folder → the main logo frames."""
    (tmp_path / "error").mkdir()
    main_dir = write_frames(tmp_path / "main", "happy")
    assert error_frames(tmp_path / "error", main_dir) == ["happy"]
    assert error_frames(tmp_path / "nowhere", main_dir) == ["happy"]


def test_plain_title_when_no_frames_exist(tmp_path: Path) -> None:
    """VC-033b: both folders empty → the plain "Octi" title (FR-032)."""
    frames = error_frames(tmp_path / "error", tmp_path / "main")
    assert frames == []
    assert "<h1>Octi</h1>" in error_screen_html("Something failed.", frames)
