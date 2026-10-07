# CLAUDE.md — Octi (TP Sistemas Multiagente I, 72.79, ITBA 2026-S2)

Two-agent QA system over tables in PDFs: **Ingestion agent** (PDF → tables → LLM metadata → Pinecone) and **Analyst agent** (question → retrieve tables → generate Python → sandboxed run → self-correct → answer with `answered` / `partial` / `cannot_answer`). Streamlit UI. Individual assignment.

**Deadline:** Wednesday 2026-10-07, 23:59. Commit timestamp must be before it.

## Ownership rule (most important)

The student must understand and be able to explain every line in an oral exam (assignment §11). Therefore:

- **Claude proposes, the student decides.** Never make a design decision silently — agent graph shape, nodes, state fields, prompts, schemas, retry limits, storage, sandbox approach, library choices. Present options with a recommendation and wait.
- Every accepted decision is logged (id, decision, alternatives, why). Project-wide decisions go in the root `DECISIONS.md` (IDs `D-NNN`); spec-local decisions go in that spec's `specs/NN-name-plan-artifacts/DECISIONS.md` (IDs `SNN-D-NNN`); decisions made while writing a spec are also folded into the spec text. If code needs a decision not in either log, stop and ask.
- Explain the *why* of each piece as it is built (RAG, tools, prompts, LangGraph state/edges), linking to the course material when relevant.
- Prefer small steps the student can review over large batches. Deadline pressure never justifies lowering quality or skipping explanation.

## Git

- **Claude never commits, pushes, or rewrites git history.** Only the student commits.
- After each plan iteration (and before finishing a plan), stop and wait for the student to review the code. Do not start the next iteration until the student says so.

## Secrets (`.env`)

- **Claude never reads, edits, copies, greps, prints or otherwise exposes `.env`** (or `.env.local`, `.env.*` except `.env.example`), not even to "check" a value. Variable names come from `.env.example`; the student manages `.env`.
- Enforced by `.claude/settings.json` (deny rules + `PreToolUse` hook `.claude/hooks/protect_env.py`). Never disable or work around it.

## Environment and dependencies

- All Python runs inside a virtual environment that **the student creates**.
- **Claude never installs or downloads anything** (no `pip install`, `uv add`, installers, `curl | sh`). Claude writes/updates the dependency file and recommends commands; the student runs them.

## Workflow: Spec-Driven Development

Follow the course's SDD method: spec 00 sets up and grounds the project; later specs refine on top of it; each plan iteration ends with all tests green and no regressions before moving on (TDD).

Per spec, in order:

1. `/write-spec` — discovery with the student, produce `specs/NN-name.md`
2. `/review-spec` — present the findings, then **stop and wait** for the student to accept, reject or adjust each one before editing the spec
3. `/write-spec-plan` — iterations in `specs/NN-name-plan.md`
4. `/implement-spec-plan` — one iteration at a time, verify acceptance criteria, then **stop and wait** for the student's review before starting the next iteration
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
