"""ASCII animation from text frames, switched instantly by the browser (D-042).

The drawing changes only in assets/logo/frame_*.txt; no row transforms or fades.
Main frames swim with a closed mouth. Error frames talk beside the speech bubble.
Python builds HTML once, without a loop or reruns. Reduced motion shows frame one.
Render with st.html so Markdown cannot rewrite the art.
"""

import html
from pathlib import Path

from services.settings import REPO_ROOT

LOGO_DIR = REPO_ROOT / "assets" / "logo"
ERROR_LOGO_DIR = LOGO_DIR / "error"
LOGO_FPS = 8


def load_frames(folder: Path) -> list[str]:
    """Read frame_*.txt in filename order. A missing folder returns no frames."""
    if not folder.is_dir():
        return []
    return [path.read_text(encoding="utf-8") for path in sorted(folder.glob("frame_*.txt"))]


def logo_html(frames: list[str], fps: int = LOGO_FPS) -> str:
    """Switch complete text frames at fps, or show a title when no frames exist."""
    if not frames:
        return '<div class="octi-logo"><h1>Octi</h1></div>'
    if fps <= 0:
        raise ValueError("Logo fps must be positive")

    lines = [frame.rstrip("\n").split("\n") for frame in frames]
    height = max(len(frame) for frame in lines)
    width = max(len(line) for frame in lines for line in frame)
    count = len(frames)
    duration = count / fps
    name = f"octi-frames-{count}"
    pres = []
    for index, frame in enumerate(lines):
        text = "\n".join(line.ljust(width) for line in frame + [""] * (height - len(frame)))
        timing = (
            f' style="animation-name: {name}; animation-duration: {duration:g}s; '
            f'animation-delay: {index / fps:g}s"' if count > 1 else ""
        )
        pres.append(f'<pre class="octi-logo-frame" aria-hidden="true"{timing}>{html.escape(text)}</pre>')

    # Only timing depends on the supplied frames; visual styling stays in styles.css.
    style = (
        f"<style>@keyframes {name} {{ 0% {{ visibility: visible; }} "
        f"{100 / count:.8f}% {{ visibility: hidden; }} 100% {{ visibility: hidden; }} }}</style>"
        if count > 1 else ""
    )
    return f'{style}<div class="octi-logo" role="img" aria-label="Octi">{"".join(pres)}</div>'
