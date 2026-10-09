"""The sidebar: logo, "New chat", model names and the start-up status (spec FR-019, FR-029)."""

import streamlit as st

from services.settings import Settings
from ui.chat import clear_conversation


def render_sidebar(settings: Settings) -> None:
    with st.sidebar:
        st.markdown("## 🐙 Octi")
        # Plain clear for now; the confirmation modal replaces it in the next iteration (FR-025).
        st.button("New chat", on_click=clear_conversation, width="stretch")

        st.caption(f"Chat model: {settings.LLM_MODEL}")  # captions, not controls: models come from .env
        st.caption(f"Embeddings: {settings.EMBEDDING_MODEL}")

        st.markdown("**Status**")
        st.markdown("✅ Configuration OK")
        st.markdown(f"✅ Pinecone index `{settings.PINECONE_INDEX_NAME}` ready")
        if settings.LANGSMITH_TRACING:
            st.markdown(f"✅ Tracing on (LangSmith project `{settings.LANGSMITH_PROJECT}`)")
        else:
            st.warning("Tracing is off: runs are not traced. Set LANGSMITH_TRACING=true in .env.")
