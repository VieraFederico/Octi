"""The animated ASCII logo (spec FR-030 … FR-032, decisions D-019, D-020, D-036, D-037).

The browser animates it with CSS; Python only builds the HTML once, so there is no loop fighting
Streamlit's rerun model. Two motions, both CSS, both crisp: text is only ever moved by whole pixels,
because a move by a fraction of a pixel makes the browser re-blur the thin characters on every frame,
which looked like static (measured, D-041). For the same reason there is no up-and-down bob.

- Swim: every row of the drawing is its own line (`.octi-row`). The tentacle rows sway sideways on
  a wave: each row starts a little later than the one above (`--phase`) and sways further the lower
  it is (`--amp`, whole pixels), so the tips ripple like Octi is swimming. The sway moves one pixel
  at a time (`steps(2 × amplitude)`).
- Mouth: the first frame is always shown. A frame that differs from it is laid on top holding only
  the rows that differ (the mouth); its other rows are blank and transparent. It appears instantly at
  its turn (`frame index / fps`) and disappears at the end of it. No fade: a fading layer dimmed
  the whole octopus once per second, which was the flicker (measured, D-041). Frames identical to the
  first add nothing and are skipped. Each drawn row has the page's background color, so it fully
  hides the row below.

The keyframes and the classes live in `assets/styles.css`; only the per-row values and the mouth
timing (which depend on the frames) are written here. Pure functions: tests read the strings.
Render the result with `st.html`, not `st.markdown`: Markdown rewrites the HTML and breaks the art.
"""

import html
from pathlib import Path

from services.settings import REPO_ROOT

LOGO_DIR = REPO_ROOT / "assets" / "logo"
ERROR_LOGO_DIR = LOGO_DIR / "error"
LOGO_FPS = 8  # code constant, not configuration (D-020)
SWIM_FROM_ROW = 26  # Octi's tentacles start around row 28 (D-035 art); start the wave just above
SWIM_MAX_AMP_PX = 5  # how far (whole px) the tentacle tips sway to each side
SWIM_ROW_DELAY_S = 0.09  # each row sways this much later than the row above: the wave travels down


def load_frames(folder: Path) -> list[str]:
    """The text of every `frame_*.txt` in `folder`, in filename order. Missing folder → no frames."""
    if not folder.is_dir():
        return []
    return [path.read_text(encoding="utf-8") for path in sorted(folder.glob("frame_*.txt"))]


def logo_html(frames: list[str], fps: int = LOGO_FPS) -> str:
    """HTML for the animated logo, or a plain "Octi" title when there are no frames (FR-032)."""
    if not frames:
        return '<div class="octi-logo"><h1>Octi</h1></div>'

    duration = len(frames) / fps  # one full loop, e.g. 3 frames at 8 fps = 0.375 s
    base = frames[0]
    pres = [f'<pre class="octi-logo-frame">{_rows(base)}</pre>']  # the base: always visible
    pres += [
        # Frame i shows at its turn, i/fps seconds into the loop. All of them share one keyframes rule.
        f'<pre class="octi-logo-frame octi-logo-overlay" style="animation-duration: {duration:g}s; '
        f'animation-delay: {index / fps:g}s; animation-name: {_mouth_keyframes_name(len(frames))}">'
        f"{_rows(frame, only_changes_from=base)}</pre>"
        for index, frame in enumerate(frames[1:], start=1)
        if frame != base  # an identical frame changes nothing on screen
    ]
    style = f"<style>{_mouth_keyframes(len(frames))}</style>" if len(frames) > 1 else ""
    return f'{style}<div class="octi-logo">{"".join(pres)}</div>'


def swim_amplitude(row: int, rows: int) -> int:
    """How far (whole px) a row sways: 0 above `SWIM_FROM_ROW`, growing to the max at the last row."""
    if row < SWIM_FROM_ROW or rows <= SWIM_FROM_ROW + 1:
        return 0
    depth = (row - SWIM_FROM_ROW + 1) / (rows - SWIM_FROM_ROW)  # just above 0 at the first row → 1 at the tips
    return max(1, round(SWIM_MAX_AMP_PX * depth**1.5))


def _rows(frame: str, only_changes_from: str | None = None) -> str:
    """One `.octi-row` per line. With `only_changes_from`, rows equal to that frame's rows are blank."""
    lines = frame.rstrip("\n").split("\n")
    base_lines = only_changes_from.rstrip("\n").split("\n") if only_changes_from is not None else None
    parts = []
    for row, line in enumerate(lines):
        if base_lines is not None and row < len(base_lines) and line == base_lines[row]:
            parts.append('<span class="octi-row octi-row-blank"> </span>')  # keeps the height, shows nothing
            continue
        text = html.escape(line, quote=True) or " "  # html.escape: frame text is shown, never run (FR-031)
        amplitude = swim_amplitude(row, len(lines))
        if amplitude:
            phase = -(row - SWIM_FROM_ROW) * SWIM_ROW_DELAY_S  # negative delay: already mid-wave at load
            # One step per pixel of travel. Written inline: CSS cannot put a variable inside steps().
            style = f"--amp: {amplitude}px; --phase: {phase:g}s; animation-timing-function: steps({2 * amplitude}, jump-none)"
            parts.append(f'<span class="octi-row octi-swim" style="{style}">{text}</span>')
        else:
            parts.append(f'<span class="octi-row">{text}</span>')
    return "".join(parts)


def _mouth_keyframes_name(frame_count: int) -> str:
    return f"octi-mouth-{frame_count}"


def _mouth_keyframes(frame_count: int) -> str:
    """Shown for one turn, hidden for the rest of the loop. The stylesheet runs it with `step-end`,
    so it switches instantly: no in-between opacity, nothing dims."""
    turn = 100 / frame_count  # % of the loop
    return f"@keyframes {_mouth_keyframes_name(frame_count)} {{ 0% {{ opacity: 1; }} {turn:.3g}% {{ opacity: 0; }} 100% {{ opacity: 0; }} }}"
