# Decisions

Log of design decisions. Every decision is made by the student; Claude proposes options.

| ID | Decision | Alternatives considered | Why |
|---|---|---|---|
| D-001 | Env var names follow the assignment (§3.2–3.3): `LITELLM_BASE_URL`, `LITELLM_API_KEY`, `LLM_MODEL`, `EMBEDDING_MODEL`, `LANGSMITH_*`, `PINECONE_*` | `LLM_SERVICE_URL` / `LLM_API_KEY` | Match the names the assignment specifies |
| D-002 | LangSmith project `octi`; Pinecone index `octi-tables` | Assignment's example names `mas-2026s2-<legajo>` / `mas-2026s2-tables` | Project name; assignment presents names as example config, not a requirement. Pinecone requires lowercase |
