"""The ASCII speech bubble Octi talks through on the error screen (spec FR-027a, D-032).

    ╭──────────────────╮
    │ What failed.     │
<───┤                  │    the tail, on the middle row, points left at Octi
    │ What to do.      │
    ╰──────────────────╯

Pure functions: `bubble_lines` builds the plain text box; `bubble_html` places the
border and text in fixed character columns. Some fallback fonts give box-drawing
glyphs a different width from letters, so a raw pre alone cannot align the border.
Below 900px CSS hides the tail/gutter and restores the plain left border.
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
    """An ASCII bubble with fixed border columns and a tail pointing towards Octi."""
    lines = bubble_lines(text, width)
    tail_row = len(lines) // 2  # always a text row: there are at least 3 lines (top, text, bottom)
    rows = []
    for index, line in enumerate(lines):
        left, body, right = line[0], line[1:-1], line[-1]
        rule = index in (0, len(lines) - 1)
        # Extra rule glyphs fill the fixed column even when a font makes ─ narrower than letters.
        content = html.escape(body * 2 if rule else body, quote=True)
        body_class = "octi-bubble-rule" if rule else "octi-bubble-text"
        if index == tail_row:
            # Wide screen: "<─────┤" replaces the left "│". Narrow screen: the CSS swaps them back.
            border = (
                f'<span class="octi-bubble-tail">{html.escape(TAIL)}┤</span>'
                '<span class="octi-bubble-notail">│</span>'
            )
        else:
            border = f'<span class="octi-bubble-gutter">{GUTTER}</span><span>{left}</span>'
        rows.append(
            f'<span class="octi-bubble-row">{border}'
            f'<span class="{body_class}">{content}</span><span>{right}</span></span>'
        )
    return f'<pre class="octi-bubble" style="--octi-bubble-columns: {width + 2}">' + "\n".join(rows) + "</pre>"
