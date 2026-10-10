"""The ASCII speech bubble of the error screen (spec FR-027a, D-032)."""

from ui.bubble import BUBBLE_WIDTH, bubble_html, bubble_lines

LONG_TEXT = (
    "The Pinecone index 'octi-tables' does not exist yet. Octi needs it before it can store any table."
    "\n\nWhat to do: run python -m scripts.setup_index, then restart the app."
)


def test_bubble_is_framed_with_box_characters() -> None:
    """VC-033a: the bubble starts with ╭ and ends with ╯; the side borders are │."""
    lines = bubble_lines(LONG_TEXT)
    assert lines[0].startswith("╭") and lines[0].endswith("╮")
    assert lines[-1].startswith("╰") and lines[-1].endswith("╯")
    assert all(line.startswith("│ ") and line.endswith(" │") for line in lines[1:-1])


def test_every_line_holds_at_most_48_characters_plus_the_frame() -> None:
    """VC-033a: text is wrapped to 48 characters; every line has the same width (text + "│ " + " │")."""
    assert BUBBLE_WIDTH == 48
    lines = bubble_lines(LONG_TEXT)
    assert {len(line) for line in lines} == {BUBBLE_WIDTH + 4}


def test_paragraphs_stay_separated_by_a_blank_line() -> None:
    """A blank line in the text stays a blank row inside the bubble, so "what to do" stands apart."""
    lines = bubble_lines("first\n\nsecond")
    inner = [line[2:-2].rstrip() for line in lines[1:-1]]
    assert inner == ["first", "", "second"]


def test_a_word_longer_than_a_line_is_split() -> None:
    """A 60-character word (e.g. a long command) cannot overflow the frame."""
    lines = bubble_lines("x" * 60)
    assert {len(line) for line in lines} == {BUBBLE_WIDTH + 4}


def test_tail_points_left_from_the_middle_row() -> None:
    """D-032: the tail sticks out of the left border on the middle row, towards Octi on the left."""
    html = bubble_html("one\ntwo\nthree")  # 5 rows: top, 3 text rows, bottom → middle = row 2 ("two")
    rows = html.split("\n")
    tail_rows = [index for index, row in enumerate(rows) if "octi-bubble-tail" in row]
    assert len(tail_rows) == 1
    assert "two" in rows[tail_rows[0]]
    assert "&lt;─────┤" in rows[tail_rows[0]]


def test_bubble_text_is_escaped() -> None:
    """VC-037 rule for the bubble: text is shown literally, never interpreted as HTML."""
    html = bubble_html('<script>alert(1)</script> & "quotes"')
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
