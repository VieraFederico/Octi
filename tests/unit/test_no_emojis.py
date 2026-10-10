"""The UI uses no emojis; icons are SVGs (decision D-036). A static scan of the UI code."""

import re

from services.settings import REPO_ROOT

# Emoji blocks: pictographs, symbols and dingbats (✅ ⚠ ✨ …), plus the variation selector that turns
# a plain symbol into an emoji. Box-drawing characters (╭ ─ ╮, the error bubble) are not in these ranges.
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️]")
UI_FILES = [REPO_ROOT / "app.py", *sorted((REPO_ROOT / "ui").glob("*.py"))]


def test_ui_code_contains_no_emojis() -> None:
    """D-036: no emoji in `app.py` or `ui/*.py`."""
    offenders = [
        f"{path.name}:{number}"
        for path in UI_FILES
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if EMOJI.search(line)
    ]
    assert offenders == []
