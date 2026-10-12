"""Pre-run catalog checks and confirmation modals (FR-102, FR-103, FR-164)."""

from collections.abc import MutableMapping
from typing import Any

import streamlit as st

from agents.ingestion.pdf.tables import document_sha
from ui.catalog import LOADED, SETTINGS, by_hash, by_name, ensure_catalog, open_library

PENDING = "pending-upload"
CONFIRMING = "upload-confirming"
IDENTICAL = "This exact file already exists in the library"


def check_upload(state: MutableMapping[str, Any], name: str, pdf: bytes) -> dict[str, Any]:
    """The hash check comes first, even if the matching bytes have another name."""
    same = by_hash(state, document_sha(pdf))
    if same:
        return {"kind": "identical", "document": same.source_file}
    previous = by_name(state, name)
    if previous:
        return {"kind": "replace", "document": name, "count": len(previous)}
    return {"kind": "start"}


def process_pending_upload(state: MutableMapping[str, Any]) -> None:
    """Run before the sidebar is drawn so busy controls are already disabled."""
    if not state.get(PENDING) or state.get(CONFIRMING):
        return
    upload = state[PENDING]
    from ui.ingestion import ACTIVE, queue_run
    if state.get(ACTIVE):
        return
    text, name = upload.get("text", ""), upload["name"]
    # AppTest injects a pending upload through this same seam as the composer.
    if not upload.get("announced"):
        from ui.chat import MESSAGES
        state.setdefault(MESSAGES, []).append({"role": "user", "content": text,
                                               "file_names": [name]})
        upload["announced"] = True
    if not state.get(LOADED) and not ensure_catalog(state, state[SETTINGS], retry=True):
        _finish_without_run(state, f"Couldn't check the library, so I didn't ingest {name}. Please try again in a moment.")
        return
    decision = check_upload(state, name, upload["pdf"])
    if decision["kind"] == "start":
        queue_run(state, upload)
        state.pop(PENDING, None)
    else:
        state[CONFIRMING] = decision


def _finish_without_run(state: MutableMapping[str, Any], sentence: str = "") -> None:
    from ui.chat import MESSAGES, QUESTION_PLACEHOLDER
    upload = state.pop(PENDING, {})
    state.pop(CONFIRMING, None)
    parts = ([sentence] if sentence else []) + ([QUESTION_PLACEHOLDER] if upload.get("text") else [])
    if parts:
        state.setdefault(MESSAGES, []).append({"role": "assistant", "content": "\n\n".join(parts)})


def _dismiss() -> None:
    decision = st.session_state.get(CONFIRMING, {})
    sentence = f"Nothing was ingested from {decision.get('document', '')}." if decision.get("kind") == "replace" else ""
    _finish_without_run(st.session_state, sentence)


def render_upload_dialog() -> None:
    decision = st.session_state.get(CONFIRMING)
    if not decision:
        return
    title = IDENTICAL if decision["kind"] == "identical" else f"Replace {decision['document']}?"

    @st.dialog(title, on_dismiss=_dismiss)
    def confirm() -> None:
        if decision["kind"] == "identical":
            st.markdown(IDENTICAL)
            if st.button("Keep", key="upload-keep"):
                _finish_without_run(st.session_state)
                st.rerun()
            if st.button("Open in library", key="upload-open"):
                open_library(st.session_state, decision["document"])
                _finish_without_run(st.session_state)
                st.rerun()
        else:
            count = decision["count"]
            st.write(f"The current version has {count} {'table' if count == 1 else 'tables'}.")
            if st.button("Cancel", key="upload-cancel"):
                _dismiss()
                st.rerun()
            if st.button("Replace", key="upload-replace", type="primary"):
                from ui.ingestion import queue_run
                queue_run(st.session_state, st.session_state.pop(PENDING))
                st.session_state.pop(CONFIRMING, None)
                st.rerun()
    confirm()
