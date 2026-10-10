"""ASCII logo: text frames, instant switching and a quiet idle mouth (D-042)."""

import html as html_module
import re
from pathlib import Path

import pytest

from ui.logo import ERROR_LOGO_DIR, LOGO_DIR, LOGO_FPS, load_frames, logo_html


def test_frames_load_in_filename_order(tmp_path: Path) -> None:
    """Frames play in filename order; unrelated files are ignored."""
    for name, text in {"frame_02.txt": "two", "frame_01.txt": "one", "frame_10.txt": "ten", "notes.md": "x"}.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    assert load_frames(tmp_path) == ["one", "two", "ten"]


def test_html_has_one_animation_lasting_frames_over_fps() -> None:
    """Three frames at 8 fps form a 0.375-second loop, without fades or transforms."""
    rendered = logo_html(["one", "two", "ten"])
    assert LOGO_FPS == 8
    assert len(re.findall(r"@keyframes ", rendered)) == 1
    assert "0.375s" in rendered
    assert rendered.index(">one") < rendered.index(">two") < rendered.index(">ten")
    assert "visibility: visible" in rendered and "visibility: hidden" in rendered
    assert "transform" not in rendered and "opacity" not in rendered


def test_frame_text_is_escaped() -> None:
    """Art containing HTML syntax is displayed literally."""
    rendered = logo_html(['<script>alert(1)</script> & "quotes"'])
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered and "&amp;" in rendered and "&quot;" in rendered


def test_missing_or_empty_folder_falls_back_to_title(tmp_path: Path) -> None:
    """An empty or missing folder shows a plain title without animation."""
    assert load_frames(tmp_path / "missing") == []
    assert load_frames(tmp_path) == []
    assert "<h1>Octi</h1>" in logo_html([])
    assert "@keyframes" not in logo_html([])


def test_idle_frames_swim_with_the_mouth_closed() -> None:
    """Every idle frame keeps the head and closed mouth; only tentacles change."""
    frames = [frame.splitlines() for frame in load_frames(LOGO_DIR)]
    assert len(frames) == 8
    assert all(frame[:26] == frames[0][:26] for frame in frames)
    assert len({tuple(frame[26:]) for frame in frames}) == 8
    assert all(len(frame) == 40 for frame in frames)
    assert max(len(line) for frame in frames for line in frame) <= 74


def test_error_frames_open_the_mouth_while_swimming() -> None:
    """The error bubble gets talking frames; head outside the mouth stays fixed."""
    frames = [frame.splitlines() for frame in load_frames(ERROR_LOGO_DIR)]
    idle = [frame.splitlines() for frame in load_frames(LOGO_DIR)]
    assert len(frames) == len(idle) == 8
    assert all(frame[:17] == idle[index][:17] for index, frame in enumerate(frames))
    assert all(frame[26:] == idle[index][26:] for index, frame in enumerate(frames))
    assert len({tuple(frame[17:26]) for frame in frames}) == 2


def test_frames_of_different_sizes_share_the_same_canvas() -> None:
    """Replacing a short frame cannot move the greeting or clip a taller frame."""
    rendered = logo_html(["x", "long\ntall"])
    texts = [html_module.unescape(text) for text in re.findall(r"<pre[^>]*>(.*?)</pre>", rendered, re.S)]
    assert texts == ["x   \n    ", "long\ntall"]


def test_single_frame_stays_still() -> None:
    assert "@keyframes" not in logo_html(["Octi"])
    assert "animation-name" not in logo_html(["Octi"])


@pytest.mark.parametrize("fps", [0, -1])
def test_nonpositive_frame_speed_is_rejected(fps: int) -> None:
    with pytest.raises(ValueError, match="positive"):
        logo_html(["Octi"], fps=fps)
