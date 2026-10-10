# Iteration 04 — Streamlit shell: theme, layout, logo, sidebar, composer

Commit SHA: (filled by student). Previous iteration (03) committed as `e459ca1`.

## Criteria
| Criterion | Command | Result |
|---|---|---|
| VC-025, 026, 026a, 027, 029, 031, 034, 035 (+ interim FR-027 / FR-028 errors, plain "New chat") | `pytest -q tests/functional/test_app.py` | PASS |
| VC-028, 028a (pure handlers; AppTest cannot upload, S00-D-018) | `pytest -q tests/unit/test_chat.py` | PASS |
| VC-036, 037, 038, 039 | `pytest -q tests/unit/test_logo.py` | PASS |
| Earlier tests still pass; suite < 30 s | `.venv/bin/python -m pytest -q` | PASS — 129 passed in 18.5 s |
| Student runs `streamlit run app.py`: empty state, composer moves, theme, logo (part of VC-043) | — | PENDING (student) |

## Files
Added: `app.py`, `ui/{startup,logo,chat,library,sidebar}.py`, `.streamlit/config.toml`,
`assets/logo/frame_01..08.txt`, `assets/logo/error/frame_01..02.txt`, `tests/unit/{test_logo,test_chat}.py`,
`tests/functional/{conftest,test_app}.py`, this record.
Changed: `tests/fakes.py` → renamed `tests/stubs.py` (student's request; imports updated) + `OK_INDEX`,
`MISSING_INDEX`; `specs/00-foundation.md` (FR-033, VC-039); root `DECISIONS.md` (D-035);
`CONTEXT.md`; `DECISIONS.md` (S00-D-017 … 019).

## Revision after the student's review (D-036)
The student ran the app and rejected the look: the ASCII Octi lost its monospace font and wrapped
(`st.markdown` rewrites HTML; now `st.html`), the toggle belonged in the sidebar, and emojis looked
cheap; status and models must open on demand, not stay on screen. Redesign: sidebar nav, footer
buttons opening Status / Models modals, centered big Octi, chat bubbles, Inter font, SVG icons only,
one global stylesheet with CSS variables and explicit classes. Added `assets/styles.css`,
`ui/style.py` (loads it), `ui/icons.py`, `assets/octi.svg`, `tests/unit/test_no_emojis.py`; changed
`app.py`, `ui/{chat,logo,sidebar}.py`, `.streamlit/config.toml`, `tests/functional/test_app.py`, spec
FR-019 / FR-026 / FR-029 / VC-025 / VC-031 / VC-034, root `DECISIONS.md` (D-036). Checked visually
with headless-Chrome screenshots at 1440×900 and 375 px (fake services). `pytest -q`: 132 passed.

Second review (D-037): the logo's "weird head" was JetBrains Mono ligatures (now off); Octi now swims
(tentacle wave + bob + mouth cross-fade, CSS only); sidebar wordmark "Octi" replaces the SVG mark;
status pops up from its button (popover); the chat model is picked in the composer from `LLM_MODEL` +
new `LLM_MODEL_CHOICES`; eased transitions everywhere. Added `tests/unit/{test_sidebar,test_style}.py`,
settings tests for the choices; changed `services/settings.py`, the env example file, spec FR-019,
FR-024a (new), FR-030, VC-025/025a/034/036 and the configuration table. `pytest -q`: 140 passed.

Third review (D-038): logo rows were centered one by one by the empty state's `text-align: center`
(the real cause of the "weird head"; ligatures were a second, smaller one); popover slide removed;
"Status: Operational"; "Octi" at the top with a "new chat" icon (Cmd/Ctrl+Shift+O); Chat | Library
pill switch. `pytest -q`: 140 passed.

Fourth review (D-039): white logo, flicker fixed (no identical-frame layers, GPU-moved rows), greeting
as HTML so it is truly centered (measured: logo, greeting and composer centers all at x = 870 at
1440 px), rounder radii. `pytest -q`: 141 passed.

Fifth review (D-040): one-screen sidebar ("Octi" home, "New chat", "Library", Documents preview with
nested tables and native expanders, status pinned to the sidebar frame). Added `ui/documents.py`,
`tests/unit/test_documents.py`. `pytest -q`: 147 passed.

Flicker (D-041), measured with a headless-Chrome screencast of the logo, one motion at a time:
the full-frame mouth fade dimmed the whole octopus each second, and sub-pixel motion (bob, eased
sway) re-blurred the text. Now: mouth-only overlay rows switching instantly, no bob, whole-pixel
stepped sway. After the fix the head rows (0-15) never change; only the mouth rows and the tentacle
tips do. `pytest -q`: 149 passed.

Gotchas from the revision:
- CSS cannot use a variable inside `steps()`; the whole animation is dropped silently. Write the
  value inline.
- Text moved by a fraction of a pixel is re-rasterized every frame and shimmers; move it by whole
  pixels or not at all.
- The stylesheet guard test caught a second `<details>` written inside a CSS comment: run it before
  looking at the app.
- A Markdown heading in Streamlit includes a hidden anchor link that offsets centered text; use HTML.
- Cross-fading two identical text layers is not invisible: the partial opacities shimmer.
- Anything inside a centered container inherits `text-align: center`; a `<pre>` then centers every
  line separately. ASCII art must set `text-align: left`.
- Streamlit positions popovers with `transform`; never animate `transform` on `stPopoverBody`.
- Streamlit's selected segmented button is styled by `.<hash>[data-selected]:not([data-disabled])`;
  to override it without `!important`, match the same attributes after the `st-key` class.
- Never write a tag-like `<word` inside `assets/styles.css`, not even in a comment: Streamlit's
  DOMPurify then drops the whole `<style>` block and every style disappears (`test_style.py` guards it).
- AppTest cannot read a popover's label; the label is a pure function (`status_label`) tested directly.
- Streamlit 1.65's selectbox is a text input plus a chevron button (not BaseWeb's select markup) and
  accepts `width` in pixels or "stretch" only.
- `st.html` strips `<svg>`; icons are `<img>` tags with an SVG `data:` URL (`ui/icons.img_tag`).
- An `st.html` holding only `<style>` goes to Streamlit's event container, so AppTest cannot see it.
  The selected nav item is therefore a "secondary" button (testable) that the stylesheet tints.
- AppTest drives `st.dialog`: clicking the footer button and reading the dialog's `st.html` works.
- Streamlit does not reload imported `ui/*` modules on a browser refresh; restart the server after edits.

## Deviations
- `ui/startup.py` and `ui/library.py` added beyond the plan's file map (S00-D-019).
- Logo frames are the student's Octi art (D-035) instead of placeholders: 8 main frames, 2 error frames.
- Before the Octi error screen exists, start-up problems use `st.error` (planned interim).

## Gotchas
- AppTest's default timeout (3 s) is too short for the first run on `/mnt/c`; use 60 s.
- Every AppTest scans installed packages for component manifests (~3 s on `/mnt/c`); the functional
  conftest skips it (S00-D-017). The first app test still takes ~12 s (cold imports).
- `st.chat_input` inside a container renders inline (AppTest root 0); at the top level it is pinned
  to the bottom (root 3). The tests use this to check FR-020 / FR-021.
- `st.cache_resource` is process-wide: tests must clear it (the `start_app` fixture does).
- Frame newlines are emitted as `&#10;`: a blank line inside a frame would otherwise end Streamlit's
  Markdown HTML block.

## For the next iteration
- Replace the `st.error` + `st.stop()` branch in `app.py` with the Octi error screen; read
  `Startup.problem` (already safe text), plus `Startup.settings is None` (configuration) vs
  `Startup.index_status.outcome` to pick the README section.
- Reuse `ui.logo.load_frames(ERROR_LOGO_DIR)` with fallback to `LOGO_DIR`, then to `logo_html([])`.
- Wire the sidebar's "New chat" to the modal; `clear_conversation()` stays the action.
