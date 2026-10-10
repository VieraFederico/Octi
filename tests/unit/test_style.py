"""The global stylesheet `assets/styles.css` (decision D-036)."""

import re

from ui.style import STYLESHEET


def test_stylesheet_has_no_tag_like_text() -> None:
    """Streamlit sanitizes `st.html` with DOMPurify, which drops a whole `<style>` block whose text looks
    like an HTML tag (for example `<input>` written in a comment). One such slip silently removes every
    style, so the sheet must not contain `<` followed by a letter or `/`."""
    css = STYLESHEET.read_text(encoding="utf-8")
    assert re.findall(r"<[A-Za-z/!]", css) == []


def test_stylesheet_braces_are_balanced() -> None:
    """A missing `}` would swallow every rule after it."""
    css = STYLESHEET.read_text(encoding="utf-8")
    assert css.count("{") == css.count("}")


def test_logo_turns_ligatures_off() -> None:
    """D-037: JetBrains Mono ligatures would redraw "===", "+++" and "::" and distort the ASCII art."""
    css = STYLESHEET.read_text(encoding="utf-8")
    assert "font-variant-ligatures: none" in css
    assert '"calt" 0' in css
