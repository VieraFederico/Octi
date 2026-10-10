"""SVG icons. The UI uses no emojis (D-036): every icon is an SVG drawn in a Catppuccin color.

`st.html` removes `<svg>` tags (it sanitizes the HTML), so pages show an icon through `img_tag`: an
`<img>` whose source is the SVG itself, written into a `data:` URL.
"""

import base64

from services.settings import REPO_ROOT

OCTOPUS_ICON = REPO_ROOT / "assets" / "octi.svg"  # the same mark as a file: the browser-tab icon

# The Octi mark: a dome head with two eyes and four curled tentacles (sidebar brand, browser tab).
OCTOPUS = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="22" height="22" fill="none"
 stroke="#cba6f7" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-label="Octi">
<path d="M7 17c0-6 4-11 9-11s9 5 9 11"/>
<path d="M7 17c-1 4-3 6-5 6M12 18c0 5-2 8-4 9M20 18c0 5 2 8 4 9M25 17c1 4 3 6 5 6"/>
<path d="M7 17h18"/>
<circle cx="12.5" cy="13" r="1.2" fill="#cba6f7" stroke="none"/>
<circle cx="19.5" cy="13" r="1.2" fill="#cba6f7" stroke="none"/>
</svg>"""

# A sheet of paper with a folded corner: a PDF in the sidebar's document list (Catppuccin subtext0).
FILE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="16" height="16" fill="none"
 stroke="#a6adc8" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-label="PDF">
<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>
</svg>"""

CHECK = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="16" height="16" fill="none"
 stroke="#a6e3a1" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-label="OK">
<circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.7 2.7L16 9.8"/>
</svg>"""

WARNING = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="16" height="16" fill="none"
 stroke="#f9e2af" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-label="Warning">
<path d="M12 3.5l9.5 16.5h-19z"/><path d="M12 10v4.5"/><circle cx="12" cy="17.3" r="0.6" fill="#f9e2af"/>
</svg>"""


def img_tag(svg: str, size: int = 16, label: str = "") -> str:
    """An `<img>` that shows `svg` at `size` pixels; `label` is the text for screen readers."""
    data = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f'<img src="data:image/svg+xml;base64,{data}" width="{size}" height="{size}" alt="{label}">'
