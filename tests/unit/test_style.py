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


def test_floating_panels_enter_without_animating_transform() -> None:
    """D-045: the status popover, the model dropdown and the modal glide in (fade, small rise and scale).
    Streamlit positions popovers with `transform`, so the entrance must use the separate `translate` /
    `scale` properties, which add to that `transform` instead of replacing it (D-038)."""
    css = STYLESHEET.read_text(encoding="utf-8")
    keyframes = re.search(r"@keyframes octi-pop-in \{(.*?)\}\s*\}", css, re.S)
    assert keyframes is not None
    assert "transform" not in keyframes.group(1)
    assert "scale:" in keyframes.group(1) and "translate:" in keyframes.group(1)
    for panel in ('[data-testid="stPopoverBody"]', '[data-testid="stSelectboxVirtualDropdown"]', '[data-testid="stDialog"]'):
        rules = [rule for rule in re.findall(r"([^{}]+)\{([^{}]*)\}", css) if panel in rule[0] and "octi-pop-in" in rule[1]]
        assert rules, f"{panel} has no octi-pop-in entrance"
