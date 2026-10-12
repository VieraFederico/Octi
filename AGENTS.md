# AGENTS.md — instructions for coding agents other than Claude Code (Codex, Cursor, …)

Octi is a two-agent question-answering system over tables in PDFs (an ITBA course assignment):
an Ingestion agent (PDF → tables → LLM metadata → Pinecone) and an Analyst agent (question →
tables → generated Python run in a Docker sandbox → answer with `answered` / `partial` /
`cannot_answer`), with a Streamlit UI.

**`CLAUDE.md` is the source of truth for this project's rules. Read it first.** This file repeats
the rules that matter most, because Claude Code's hooks and skills do not run in other tools.

## Hard rules

1. **Never read, open, print, copy, search or edit `.env`, `.env.local` or any `.env.*` file**
   (only `.env.example` may be read). They hold API keys. Do not run commands that would print
   them (`cat`, `grep`, `env`, `printenv`, debugging prints of settings). Variable names come from
   `.env.example`.
2. **Never commit, push or rewrite git history.** The student commits. When you finish, list the
   exact files you created, changed or deleted.
3. **Never install or download anything** (no `pip install`, package managers, installers, image
   pulls). Propose the command; the student runs it.
4. **Never edit** root `DECISIONS.md`, `CONTEXT.md`, `CLAUDE.md` or any `specs/*.md` unless the
   student asks you to by name. A design choice not covered by the spec, its plan or a logged
   decision belongs to the student: stop and ask.
5. **Default to read-only.** If you were asked to review, do not edit files.

## How the project works

- Spec-Driven Development: `specs/NN-name.md` (requirements FR/BR/NFR and verification criteria
  VC), `specs/NN-name-plan.md` (iterations), `specs/NN-name-plan-artifacts/` (CONTEXT.md,
  DECISIONS.md, iteration records). Follow the plan's Artifact Protocol when implementing.
- Decisions: project-wide in root `DECISIONS.md` (`D-NNN`), spec-local in the plan artifacts
  (`SNN-D-NNN`).
- Glossary: `CONTEXT.md` (Table, Table metadata, Table store, Index record, Document, …).
- Tests run offline, with stubs, never against live services or a live model:
  `.venv/bin/python -m pytest -q`. Live checks (`pytest -m live`, the app) are run by the student.
- Test-driven: write the test first and see it fail.
- All LLM and embedding calls go through the university LiteLLM proxy; generated code runs only in
  the Docker sandbox; user-facing messages never name backend services.
- Code, comments, commits and docs are in English, neutral and professional.
