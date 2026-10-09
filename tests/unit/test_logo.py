"""ASCII logo: frames from a folder, animated by CSS (spec FR-030 … FR-033)."""

import re
from pathlib import Path

from services.settings import REPO_ROOT
from ui.logo import LOGO_FPS, load_frames, logo_html


def write_frames(folder: Path, frames: dict[str, str]) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for name, text in frames.items():
        (folder / name).write_text(text, encoding="utf-8")
    return folder


def test_frames_load_in_filename_order(tmp_path: Path) -> None:
    """VC-036: frame_02, frame_01, frame_10 → order 01, 02, 10; other files are ignored."""
    folder = write_frames(
        tmp_path, {"frame_02.txt": "two", "frame_01.txt": "one", "frame_10.txt": "ten", "notes.md": "x"}
    )
    assert load_frames(folder) == ["one", "two", "ten"]


def test_html_has_one_animation_lasting_frames_over_fps() -> None:
    """VC-036: 3 frames at 8 fps → one CSS animation of 0.375 s, frames in order."""
    html = logo_html(["one", "two", "ten"])
    assert LOGO_FPS == 8
    assert len(re.findall(r"@keyframes ", html)) == 1
    assert "0.375s" in html
    assert html.index("one") < html.index("two") < html.index("ten")


def test_frame_text_is_escaped() -> None:
    """VC-037: `<script>&"` is shown literally, never interpreted as HTML."""
    html = logo_html(['<script>alert(1)</script> & "quotes"'])
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "&amp;" in html
    assert "&quot;" in html


def test_missing_or_empty_folder_falls_back_to_title(tmp_path: Path) -> None:
    """VC-038: empty or missing folder → no frames → plain "Octi" title, no exception."""
    assert load_frames(tmp_path / "does-not-exist") == []
    assert load_frames(tmp_path) == []
    html = logo_html([])
    assert "Octi" in html
    assert "@keyframes" not in html


def test_repo_ships_the_octi_frames() -> None:
    """VC-039: main logo = 8 frames, mouth closed in 7 and open in the last; error logo = closed + open."""
    main_frames = load_frames(REPO_ROOT / "assets" / "logo")
    error_frames = load_frames(REPO_ROOT / "assets" / "logo" / "error")
    closed, opened = main_frames[0], main_frames[-1]
    assert len(main_frames) == 8
    assert main_frames[:7] == [closed] * 7
    assert opened != closed
    assert error_frames == [closed, opened]
