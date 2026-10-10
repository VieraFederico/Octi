"""The sidebar's document preview: each ingested PDF with its first tables (spec FR-026a, D-040).

Pure functions that return HTML, so tests read them without Streamlit. "View all" (more tables of one
PDF) and "Show more" (more PDFs) use the browser's own `<details>` element: they open instantly, with
no Streamlit rerun and no session state.

Until the Ingestion agent exists (spec 01) there are no documents; `load_documents()` is the seam
spec 01 replaces with a real read of the index.
"""

import html
from dataclasses import dataclass, field

from ui.icons import FILE, img_tag

TABLES_SHOWN = 3  # tables listed under a PDF before "View all"
DOCUMENTS_SHOWN = 5  # PDFs listed before "Show more"
EMPTY_DOCUMENTS = "No documents yet. Attach a PDF in the chat to add one."


@dataclass(frozen=True)
class DocumentPreview:
    name: str  # the PDF's file name
    tables: list[str] = field(default_factory=list)  # titles of the tables extracted from it


def load_documents() -> list[DocumentPreview]:
    """The ingested PDFs, newest first. Empty until spec 01 adds ingestion."""
    return []


def documents_html(documents: list[DocumentPreview]) -> str:
    """The "Documents" section: a heading, then the PDFs (or an empty-state line)."""
    heading = '<div class="octi-section-title">Documents</div>'
    if not documents:
        return f'<div class="octi-docs">{heading}<div class="octi-docs-empty">{EMPTY_DOCUMENTS}</div></div>'
    first = "".join(_document(document) for document in documents[:DOCUMENTS_SHOWN])
    rest = documents[DOCUMENTS_SHOWN:]
    more = _expander("Show more", "".join(_document(document) for document in rest), "octi-more-docs") if rest else ""
    return f'<div class="octi-docs">{heading}{first}{more}</div>'


def _document(document: DocumentPreview) -> str:
    title = f'<div class="octi-doc-title">{img_tag(FILE)}<span>{html.escape(document.name)}</span></div>'
    if not document.tables:
        return f'<div class="octi-doc">{title}</div>'
    tables = "".join(_table(name) for name in document.tables[:TABLES_SHOWN])
    hidden = document.tables[TABLES_SHOWN:]
    view_all = _expander("View all", "".join(_table(name) for name in hidden), "octi-more-tables") if hidden else ""
    return f'<div class="octi-doc">{title}<div class="octi-doc-tables">{tables}{view_all}</div></div>'


def _table(name: str) -> str:
    return f'<div class="octi-doc-table">{html.escape(name)}</div>'


def _expander(label: str, content: str, css_class: str) -> str:
    """A `<details>` block. The stylesheet draws the summary below the content, so the clickable line
    stays at the end of the list, and swaps its text to "Show less" while open."""
    summary = f'<summary><span class="octi-closed-label">{label}</span><span class="octi-open-label">Show less</span></summary>'
    return f'<details class="{css_class}">{summary}<div class="octi-expanded">{content}</div></details>'
