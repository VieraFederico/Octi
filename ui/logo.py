"""The animated ASCII logo (spec FR-030 … FR-032, decisions D-019, D-020).

The browser animates it: every frame is placed in the same grid cell, and one CSS animation shows
each frame in turn. Python only builds the HTML once, so there is no loop fighting Streamlit's
rerun model. Pure functions: they return strings, which tests read without running Streamlit.
"""

import html
from pathlib import Path

from services.settings import REPO_ROOT

LOGO_DIR = REPO_ROOT / "assets" / "logo"
ERROR_LOGO_DIR = LOGO_DIR / "error"
LOGO_FPS = 8  # code constant, not configuration (D-020)
MAUVE = "#cba6f7"


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
    visible_share = 100 / len(frames)  # each frame is visible for this % of the loop
    pres = "".join(
        # Frame i waits i/fps seconds before its turn. html.escape: frame text is shown, never run (FR-031).
        # Newlines become &#10; so a blank line in a frame cannot end Streamlit's Markdown HTML block.
        f'<pre style="animation-delay: {index / fps:g}s">{_escape(frame)}</pre>'
        for index, frame in enumerate(frames)
    )
    return f"""
<style>
.octi-logo {{ display: inline-grid; color: {MAUVE}; }}
.octi-logo pre {{
  grid-area: 1 / 1;            /* all frames share one cell: they overlap exactly */
  margin: 0; background: transparent; color: inherit; font-size: 0.45rem; line-height: 1;
  opacity: 0;
  animation: octi-frame {duration:g}s step-end infinite;
}}
@keyframes octi-frame {{ 0% {{ opacity: 1; }} {visible_share:g}% {{ opacity: 0; }} }}
</style>
<div class="octi-logo">{pres}</div>
"""


def _escape(frame: str) -> str:
    return html.escape(frame.rstrip("\n"), quote=True).replace("\n", "&#10;")
