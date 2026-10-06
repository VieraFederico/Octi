# CLAUDE.md — Octi (TP Sistemas Multiagente I, 72.79, ITBA 2026-S2)

Two-agent QA system over tables in PDFs: **Ingestion agent** (PDF → tables → LLM metadata → Pinecone) and **Analyst agent** (question → retrieve tables → generate Python → sandboxed run → self-correct → answer with `answered` / `partial` / `cannot_answer`). Streamlit UI. Individual assignment.

**Deadline:** Wednesday 2026-10-07, 23:59. Commit timestamp must be before it.

## Ownership rule (most important)

The student must understand and be able to explain every line in an oral exam (assignment §11). Therefore:

- **Claude proposes, the student decides.** Never make a design decision silently — agent graph shape, nodes, state fields, prompts, schemas, retry limits, storage, sandbox approach, library choices. Present options with a recommendation and wait.
- Every accepted decision is logged in `DECISIONS.md` (id, decision, alternatives, why). If code needs a decision not in the log, stop and ask.
- Explain the *why* of each piece as it is built (RAG, tools, prompts, LangGraph state/edges), linking to the course material when relevant.
- Prefer small steps the student can review over large batches. Deadline pressure never justifies lowering quality or skipping explanation.

## Git

- **Claude never commits, pushes, or rewrites git history.** Only the student commits.
- After each plan iteration (and before finishing a plan), stop and wait for the student to review the code. Do not start the next iteration until the student says so.

## Workflow: Spec-Driven Development

Follow the course's SDD method: spec 00 sets up and grounds the project; later specs refine on top of it; each plan iteration ends with all tests green and no regressions before moving on (TDD).

Per spec, in order:

1. `/write-spec` — discovery with the student, produce `specs/NN-name.md`
2. `/review-spec` — fix gaps before planning
3. `/write-spec-plan` — iterations in `specs/NN-name-plan.md`
4. `/implement-spec-plan` — one iteration at a time, verify acceptance criteria, student reviews each iteration
5. `/verify-spec` — end-to-end check against the spec

Do not start a spec before the previous one is verified, unless the student says so.

## Hard constraints from the assignment

The assignment is the source of truth; when anything conflicts with it, the assignment wins. Credit any external code, tutorial, or template used (assignment §11).

- Stack: Streamlit, LangGraph (`StateGraph`), LangChain, Pinecone, LangSmith, Python 3.11+.
- **All** LLM and embedding calls go through the university LiteLLM proxy (OpenAI-compatible, `langchain_openai`).
- Every agent run traced in LangSmith, each graph node visible as a span.
- Secrets only in `.env` (never committed); versioned `.env.example`. Never print keys or raw LiteLLM error bodies.
- Generated code runs isolated from the Streamlit process, with timeout, no network, no filesystem beyond table data.
- Re-ingesting the same PDF creates no duplicates in Pinecone (idempotent `table_id`s).
- Answerability status decided by agent logic and stored in graph state (testable), not left to final-answer wording.

## Conventions

- Tests run offline: stub the LLM and embeddings; never assert a live model's output in tests.
- Code and commits in English.
