"""The sidebar's document preview: each ingested PDF with its first tables (spec FR-026a, D-040).

Pure functions that return HTML, so tests read them without Streamlit. "View all" (more tables of one
PDF) and "Show more" (more PDFs) use the browser's own `<details>` element: they open instantly, with
no Streamlit rerun and no session state.

`load_documents()` reads the session catalog. A local v2 component sends Document clicks to
Streamlit while the existing browser-owned expanders keep opening without a rerun (S01-D-024).
"""

import html
from dataclasses import dataclass, field

import streamlit as st

from ui.catalog import LOADED, LOAD_FAILURE, documents, open_library

from ui.icons import FILE, img_tag

TABLES_SHOWN = 3  # tables listed under a PDF before "View all"
DOCUMENTS_SHOWN = 5  # PDFs listed before "Show more"
EMPTY_DOCUMENTS = "No documents yet. Attach a PDF in the chat to add one."


@dataclass(frozen=True)
class DocumentPreview:
    name: str  # the PDF's file name
    tables: list[str] = field(default_factory=list)  # titles of the tables extracted from it


def load_documents() -> list[DocumentPreview]:
    """The ingested PDFs, newest first, without another catalog read."""
    return [DocumentPreview(name, [entry.name for entry in entries]) for name, entries in documents(st.session_state)]


def documents_html(documents: list[DocumentPreview], *, navigable: bool = False, disabled: bool = False) -> str:
    """The "Documents" section: a heading, then the PDFs (or an empty-state line)."""
    heading = '<div class="octi-section-title">Documents</div>'
    if not documents:
        return f'<div class="octi-docs">{heading}<div class="octi-docs-empty">{EMPTY_DOCUMENTS}</div></div>'
    first = "".join(_document(document, navigable, disabled) for document in documents[:DOCUMENTS_SHOWN])
    rest = documents[DOCUMENTS_SHOWN:]
    more = _expander("Show more", "".join(_document(document, navigable, disabled) for document in rest), "octi-more-docs") if rest else ""
    return f'<div class="octi-docs">{heading}{first}{more}</div>'


def _document(document: DocumentPreview, navigable: bool = False, disabled: bool = False) -> str:
    title = f'<div class="octi-doc-title">{img_tag(FILE)}<span>{html.escape(document.name)}</span></div>'
    if navigable:
        inactive = ' disabled' if disabled else ''
        title = (f'<button class="octi-doc-title" data-document="{html.escape(document.name, quote=True)}"{inactive}>'
                 f'{img_tag(FILE)}<span>{html.escape(document.name)}</span></button>')
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


DOCUMENTS_JS = """
export default function(component) {
    const { data, parentElement, setTriggerValue } = component;
    const root = parentElement.querySelector('[data-documents-root]');
    root.innerHTML = data;
    const click = (event) => {
        const button = event.target.closest('button[data-document]');
        if (button && !button.disabled) {
            setTriggerValue('document', button.dataset.document);
        }
    };
    root.addEventListener('click', click);
    return () => root.removeEventListener('click', click);
}
"""

def render_documents(*, disabled: bool = False) -> None:
    if not st.session_state.get(LOADED):
        st.html(f'<div class="octi-docs"><div class="octi-section-title">Documents</div>{html.escape(LOAD_FAILURE)}</div>')
        return
    previews = load_documents()
    if not previews:
        st.html(documents_html([]))
        return
    # Register in the active app runtime, rather than at import time (AppTest creates runtimes).
    component = st.components.v2.component(
        "octi_documents", html='<div data-documents-root></div>', js=DOCUMENTS_JS, isolate_styles=False,
    )
    # Every variable field has been escaped in documents_html; only this trusted shell runs JS.
    result = component(data=documents_html(previews, navigable=True, disabled=disabled),
                       key="sidebar-documents", on_document_change=lambda: None)
    name = result.document
    if name and not disabled and any(document.name == name for document in previews):
        open_library(st.session_state, name)
