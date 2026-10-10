"""The ASCII speech bubble Octi talks through on the error screen (spec FR-027a, D-032).

    ╭──────────────────╮
    │ What failed.     │
<───┤                  │    the tail, on the middle row, points left at Octi
    │ What to do.      │
    ╰──────────────────╯

Pure functions: `bubble_lines` builds the box as plain text (tests read it); `bubble_html` adds the
tail and escapes the text. Below 640 px the bubble sits under Octi, so `assets/styles.css` hides
the tail and the gutter, and shows a plain `│` in the tail's place.
"""

import html
import textwrap

BUBBLE_WIDTH = 48  # characters of text per line; code constant, not configuration (D-032)
TAIL = "<─────"  # the tail's stem; the bubble's left border becomes "┤" where it attaches
GUTTER = " " * len(TAIL)  # the space the tail takes on every other row, so the box stays aligned


def bubble_lines(text: str, width: int = BUBBLE_WIDTH) -> list[str]:
    """`text` wrapped to `width` and framed. Each `\\n` starts a new line; a blank line stays blank."""
    wrapped = [
        part
        for line in text.split("\n")
        # break_on_hyphens=False keeps names like "octi-tables" whole; a word longer than the line
        # (a long command) is still split, so nothing overflows the frame.
        for part in (textwrap.wrap(line, width, break_on_hyphens=False) or [""])
    ]
    top = "╭" + "─" * (width + 2) + "╮"
    bottom = "╰" + "─" * (width + 2) + "╯"
    return [top, *(f"│ {part.ljust(width)} │" for part in wrapped), bottom]


def bubble_html(text: str, width: int = BUBBLE_WIDTH) -> str:
    """The bubble as one `<pre>`, with the tail on the middle row. Render it with `st.html`."""
    lines = bubble_lines(text, width)
    tail_row = len(lines) // 2  # always a text row: there are at least 3 lines (top, text, bottom)
    rows = []
    for index, line in enumerate(lines):
        escaped = html.escape(line, quote=True)  # the text is shown, never run (same rule as the logo)
        if index == tail_row:
            # Wide screen: "<─────┤" replaces the left "│". Narrow screen: the CSS swaps them back.
            rows.append(
                f'<span class="octi-bubble-tail">{html.escape(TAIL)}┤</span>'
                f'<span class="octi-bubble-notail">│</span>{escaped[1:]}'
            )
        else:
            rows.append(f'<span class="octi-bubble-gutter">{GUTTER}</span>{escaped}')
    return '<pre class="octi-bubble">' + "\n".join(rows) + "</pre>"
