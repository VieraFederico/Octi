"""ASCII logo: frames from a folder, animated by CSS (spec FR-030 … FR-033)."""

import re
from pathlib import Path

from services.settings import REPO_ROOT
from ui.logo import LOGO_FPS, SWIM_FROM_ROW, SWIM_MAX_AMP_PX, load_frames, logo_html, swim_amplitude


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


def test_only_tentacle_rows_swim_and_tips_swim_most() -> None:
    """VC-036 (D-037): rows above the tentacles stay still; the sway grows row by row to the tips."""
    rows = 40
    amplitudes = [swim_amplitude(row, rows) for row in range(rows)]
    assert all(amplitude == 0 for amplitude in amplitudes[:SWIM_FROM_ROW])
    tentacles = amplitudes[SWIM_FROM_ROW:]
    assert all(amplitude > 0 for amplitude in tentacles)
    assert tentacles == sorted(tentacles) and tentacles[-1] == SWIM_MAX_AMP_PX


def test_every_row_is_its_own_line_and_tentacle_rows_carry_their_wave() -> None:
    """VC-036 (D-037): each text line becomes one `.octi-row`; tentacle rows get `--amp` and `--phase`."""
    frame = "\n".join(f"row{index}" for index in range(40))
    html = logo_html([frame])
    assert html.count('class="octi-row') == 40
    assert html.count("octi-swim") == 40 - SWIM_FROM_ROW
    assert "--amp:" in html and "--phase:" in html and "steps(" in html


def test_frames_identical_to_the_first_are_not_layered() -> None:
    """D-039: closed, closed, closed, open → only the "open" frame fades over the base; fading a copy
    of the base over itself only made the text shimmer."""
    html = logo_html(["closed", "closed", "closed", "open"])
    assert html.count("octi-logo-overlay") == 1
    assert html.count("<pre") == 2


def test_swim_amplitudes_are_whole_pixels() -> None:
    """D-041: rows move by whole pixels only; a fraction of a pixel re-blurs the text (shimmer)."""
    assert all(isinstance(swim_amplitude(row, 40), int) for row in range(40))


def test_overlay_frames_draw_only_the_rows_that_change() -> None:
    """D-041: an overlay frame repeats nothing from the base: unchanged rows are blank, so showing it
    never dims the rest of the octopus."""
    html = logo_html(["a\nmouth closed\nc", "a\nmouth OPEN\nc"])
    overlay = html.split("octi-logo-overlay", 1)[1]
    assert "mouth OPEN" in overlay
    assert overlay.count("octi-row-blank") == 2
    assert ">a<" not in overlay and ">c<" not in overlay
