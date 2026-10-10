# Spec 00 — Foundation

- **Version:** 0.7
- **Last updated:** 2026-10-10
- **Status:** Implemented and verified (`/verify-spec` PASSED, 2026-10-10)
- **Owner:** Federico Viera
- **Changelog:** v0.7 — UI reviews during Iterations 4–6 (D-035 … D-042: sidebar, model picker, logo
  frames, neutral palette and radii, error screen stacks below 900 px), "New chat" always shows the
  Chat view (FR-025c), README without page map (D-043, VC-042), picker not typeable and smoother
  panels (D-045), VC-011 covers BR-011 by review. v0.6 — error bases are ordinary classes (FR-007a
  removed), missing index is a status not an error, logging coverage scoped to Octi's handler,
  retries "3 by default", independent service checks (FR-017, VC-022a), one live smoke test that
  runs the service check (FR-035), A-006.
- **Decisions:** root `DECISIONS.md` D-001 … D-045 (project-wide). Spec-local decisions made during
  planning/implementation go to `specs/00-foundation-plan-artifacts/DECISIONS.md` as `S00-D-NNN` (D-004).
- **Glossary:** `CONTEXT.md`

## 1. Purpose

Octi answers questions about tables inside machine-readable PDFs with two LangGraph agents
(assignment §1). Before either agent exists, the project needs a foundation every later spec builds
on: a reproducible setup, typed and safe configuration, factories for the university LiteLLM proxy,
tracing, the Pinecone index, an explicit error vocabulary, an offline test harness, a way to prove
all external services work, and the chat-first Streamlit shell the agents will plug into. This spec
delivers exactly that and nothing agent-specific. It benefits the student (a working, explainable
base before the deadline) and the graders (a setup they can reproduce and verify in minutes).

## 2. Scope

### In
- Folder layout per D-008 plus `scripts/`, `assets/logo/`, `specs/`, `.streamlit/`.
- Pinned `requirements.txt` (D-006), Python `>=3.11` (D-007).
- Configuration: `load_dotenv()` + typed Pydantic `Settings` (D-013, D-017).
- Factories for the chat model and the embeddings model through the proxy (D-021).
- LangSmith tracing enabled from the environment.
- Error hierarchy (D-027) and logging with secret redaction (D-018).
- One-time Pinecone index setup script and a startup index check (D-010, D-014).
- Service-check script (D-012).
- Offline pytest harness with stubs; `live`-marked smoke tests excluded by default (D-011).
- Streamlit shell: chat-first single page, `Chat | Library` toggle, sidebar, composer with "+",
  placeholder replies, CSS-animated ASCII logo (D-016, D-019, D-020), one conversation per session,
  Catppuccin Mocha theme (D-029), "New chat" confirmation (D-030), Octi error screen (D-031, D-032).
- README setup section (D-023).

### Out
- Table store, PDF extraction, ingestion graph, metadata enrichment, indexing of tables (spec 01).
- Sandbox, analyst graph, answerability logic (spec 02).
- Agent retry limits (D-022: specs 01/02).
- Evaluation, architecture diagrams, design-decision README sections, bonus features (spec 03).
- Visual polish beyond the Catppuccin Mocha theme; final logo frames (student, later).
- Persistent or multiple conversations; authentication; deployment.
- Any change that makes `.env` readable to Claude (CLAUDE.md "Secrets").

## 3. Actors

| Actor | Description | Permissions |
|---|---|---|
| Student / developer | Sets up the environment, owns `.env`, runs scripts and tests | Full access to the repo and `.env` |
| App user | Uses the Streamlit UI in a browser | Upload PDFs and type questions in the UI only; never sees configuration or secrets |
| Grader | Clones the repo and follows the README | Same as student, with their own `.env` |
| External services | LiteLLM proxy, Pinecone, LangSmith | Receive only the calls Octi makes |

## 4. Functional Requirements

### Configuration
- **FR-001 (Must)** — Given a `.env` with every required variable, When the app or a script starts, Then the
  `.env` at the repository root (resolved from the code's location, not the current working
  directory) is loaded into the process environment without overriding variables already set in the
  shell, and a typed `Settings` object is built once and reused for the rest of the process.
- **FR-002 (Must)** — Given one or more required variables missing or invalid, When `Settings` is
  built, Then a `InvalidSettingsError` is raised whose message lists every offending variable **name** and the
  reason (missing / invalid format), and contains no variable **value**.
- **FR-003 (Must)** — Given `LITELLM_BASE_URL` with or without a trailing `/` or `/v1`, When parsed,
  Then the stored base URL ends in exactly one `/v1`.
- **FR-004 (Must)** — Given `Settings`, When it is printed, logged, or included in an exception, Then
  every secret field (`LITELLM_API_KEY`, `PINECONE_API_KEY`, `LANGSMITH_API_KEY`) renders masked.
- **FR-004a (Must)** — Given a secret field shorter than 8 characters, When `Settings` is built, Then a
  `InvalidSettingsError` names that field (a secret that short cannot be redacted safely from log text).

### Model factories
- **FR-005 (Must)** — Given valid `Settings`, When the chat-model factory is called, Then it returns a
  LangChain chat model pointed at the proxy base URL with `LLM_MODEL`, `LLM_TEMPERATURE`,
  `LLM_TIMEOUT_SECONDS` and `LLM_MAX_RETRIES` from `Settings`.
- **FR-006 (Must)** — Given valid `Settings`, When the embeddings factory is called, Then it returns a
  LangChain embeddings model pointed at the proxy base URL with `EMBEDDING_MODEL`, the same timeout
  and retry settings, and plain-string inputs (no client-side tokenization).

### Errors and logging
- **FR-007 (Must)** — The codebase declares the error hierarchy of D-027 (tree in §7). Group classes
  exist so callers can catch a family; Octi code raises the specific **leaf** classes, each carrying
  a user-safe message (`user_message`); every `ExternalServiceError` descendant exposes which service
  failed (`service`). Groups are ordinary classes: nothing enforces "leaves only" at runtime.
- **FR-008 (Must)** — Given a failure inside an external client call made by spec-00 code (the index
  check, the setup script, the service check), Then it is re-raised as the matching leaf error
  (connection error or timeout → `*UnreachableError`; rejected credentials → `*AuthenticationError`;
  missing model → `ModelNotAvailableError`; wrong vector length → `EmbeddingDimensionError`; wrong
  dimension/metric → `IndexMismatchError`) with the original exception chained as its cause. A
  missing index is not an error: it is the `missing` status of FR-014. (Agent calls adopt the same
  rule in specs 01/02.)
- **FR-009 (Must)** — Given logging is configured, When a log record is emitted through Octi's own
  handler and its text contains the value of a secret field, Then the emitted line shows `***` in its
  place. Handlers installed by other libraries are not covered; the first defense remains never
  logging secrets (`SecretStr`, BR-003).
- **FR-010 (Should)** — Given `LOG_LEVEL` is set to a valid level name, When logging is configured,
  Then that level is used; otherwise `INFO`.

### Pinecone index
- **FR-011 (Must)** — Given valid `Settings` and no index named `PINECONE_INDEX_NAME`, When the setup
  script runs, Then it creates a serverless index with dimension `EMBEDDING_DIMENSION`, metric
  cosine, on the free-plan location `aws` / `us-east-1` (code constants), and reports that it was
  created.
- **FR-012 (Must)** — Given the index already exists with the expected dimension and metric, When the
  setup script runs, Then it changes nothing and reports that it already exists.
- **FR-013 (Must)** — Given the index exists with a different dimension or metric, When the setup
  script runs, Then it changes nothing, exits non-zero, and reports the expected vs actual values.
- **FR-014 (Must)** — Given the app starts, When the index check runs, Then it reports exactly one of:
  `ok`; `missing` (with the setup command to run); `mismatch` (expected vs actual dimension/metric);
  `unreachable` (Pinecone could not be reached or rejected the API key, with a safe reason) — never
  creating or modifying the index itself.

### Service check
- **FR-015 (Must)** — Given the service-check script runs, Then it reports exactly one line per check,
  each `OK` or `FAIL: <safe reason>`, for: configuration, LiteLLM models (the proxy's model list
  contains `LLM_MODEL` and `EMBEDDING_MODEL`), LiteLLM chat (one minimal completion),
  LiteLLM embeddings (one embedding whose length equals `EMBEDDING_DIMENSION`), Pinecone index
  (exists, dimension, metric), LangSmith (authenticated request succeeds and tracing is enabled).
- **FR-016 (Must)** — Safety net against a future accident (today the file is git-ignored and
  untracked): Given the service-check script runs and the secrets file has been added to git, Then it
  reports a `FAIL` line telling the user to untrack it; given it is not tracked, the line reads `OK`; given the folder is not a git repository, the
  line reads `skipped (not a git repository)`.
- **FR-017 (Must)** — Given any check fails, Then the remaining checks still run and the script exits
  non-zero; given all pass, it exits zero. Each check builds the client it needs inside its own
  guarded step, so a client that cannot even be built fails only the check that uses it.
- **FR-018 (Must)** — Given configuration is invalid, Then the configuration line shows the
  `InvalidSettingsError` field names and the dependent checks are reported as skipped.

### Streamlit shell
- **FR-019 (Must)** — Given valid configuration and index status `ok`, When the app opens, Then it
  shows a single page
  with a sidebar on one screen (D-040), from the top: the wordmark "Octi" (Inter, extra bold; clicking
  it returns to the current chat); the rows "New chat" (shortcut Cmd/Ctrl+Shift+O) and "Library" (the
  Library view; highlighted while open); the Documents preview (FR-026a); and, at the bottom, a status
  button ("Status: Operational", or "Status: Not traced") whose popover opens from it with the startup
  status (configuration OK, the FR-014 index status, the tracing status (FR-029)) and the embedding
  model name (shown, not chosen). The status is
  not on screen until opened. The UI uses no emojis; icons are SVGs (D-036, D-037). The startup status makes no LiteLLM call; the full service check stays in the script
  (D-025).
- **FR-020 (Must)** — Given the conversation is empty, When the Chat view renders, Then it shows, in
  this vertical order and all horizontally and vertically centered: the animated ASCII logo, a
  greeting, and the composer (inline, directly below the greeting) (D-028).
- **FR-021 (Must)** — Given the conversation has at least one message, When the Chat view renders,
  Then the logo and greeting are not shown, the message history is shown, and the composer is pinned
  to the bottom of the page (D-028).
- **FR-019a (Must)** — The UI uses the Catppuccin Mocha palette: background base `#1e1e2e`, secondary
  background mantle `#181825`, text and neutral control accent `#cdd6f4` (buttons, focus, links),
  errors Red `#f38ba8`, warnings Yellow `#f9e2af`; the ASCII logo is white. Controls use a
  0.75rem radius and panels, composer and user messages use 1rem (D-042, amending D-029/D-039).
  The empty-chat composer is at least 120px tall with attachment, model picker and send along its lower edge.
- **FR-022 (Must)** — Given the user submits text in the composer, Then the text appears as a user
  message followed by an assistant message stating that answering arrives in spec 02.
- **FR-023 (Must)** — Given the user attaches a PDF with the composer's "+", Then a user message shows
  the file name and an assistant message states that ingestion arrives in spec 01; the file is not
  stored.
- **FR-023a (Should)** — Given the user submits text and a PDF together, Then one user message shows
  both the text and the file name, and the assistant reply contains both placeholders (FR-023 then
  FR-022).
- **FR-024 (Must)** — Given the composer, When the user tries to attach a non-PDF file, Then the
  upload is not accepted.
- **FR-024a (Must)** — The composer shows a chat-model picker at its right end, offering `LLM_MODEL`
  (first, the default) and then the models in `LLM_MODEL_CHOICES`, without duplicates. The pick is
  kept for the browser session, survives the move from the empty state to the pinned composer, and
  is what the Analyst agent (spec 02) will use. The embedding model is not selectable (D-037).
- **FR-025 (Must)** — Given messages exist and warnings are enabled, When the user clicks "New chat",
  Then a modal says the current conversation will be erased and offers **Erase**, **Cancel** and a
  "Don't warn me again" checkbox (D-030).
- **FR-025a (Must)** — Given the modal, When the user clicks **Erase**, Then the conversation is
  cleared, the empty state (FR-020) returns, and, if the checkbox was ticked, warnings are disabled for
  the rest of the browser session; When the user clicks **Cancel**, Then nothing changes (the checkbox
  is ignored).
- **FR-025b (Must)** — Given warnings are disabled for this session, When the user clicks "New chat"
  with messages, Then the conversation is cleared immediately, without a modal.
- **FR-025c (Must)** — Given the conversation is empty, When the user clicks "New chat", Then no modal
  appears and the conversation does not change. In every case "New chat" shows the Chat view (from
  Library too); the modal, when there is one, opens over it (S00-D-023).
- **FR-026a (Must)** — The sidebar's "Documents" section lists the ingested PDFs (5 shown, the rest
  behind "Show more"), each with up to 3 of its table titles nested under it (the rest behind
  "View all"); both expanders open in place without a rerun and read "Show less" while open. Names are
  HTML-escaped. Before spec 01 there are no documents and it reads "No documents yet" (D-040).
- **FR-026 (Must)** — Given the Library view is selected (sidebar "Library" row), Then it shows an empty-state message saying
  no tables are indexed yet.
- **FR-027 (Must)** — Given configuration is invalid, When the app opens, Then the Octi error screen
  (FR-027a) is shown instead of the shell, naming the offending variables (names only) and telling
  the user to fix `.env` from `.env.example` and restart; the app does not crash (D-031).
- **FR-028 (Must)** — Given the startup index status is `missing`, `mismatch` or `unreachable`, When the
  app opens, Then the Octi error screen is shown instead of the shell, stating what failed (FR-014
  reason) and what to do (`missing` → run the setup script; `mismatch` → expected vs actual and how to
  fix; `unreachable` → check network / `PINECONE_API_KEY`) (D-031).
- **FR-027a (Must)** — The Octi error screen shows the animated Octi on the left and an ASCII speech
  bubble on the right: text wrapped to at most 48 characters per line, framed with box characters
  (`╭ ─ ╮ │ ╰ ╯`) and a tail pointing at Octi. The bubble contains: what failed, what to do, and the
  README section to read; never a secret value or raw library text (D-032).
- **FR-027b (Must)** — Given a viewport narrower than 900 px, Then the speech bubble renders below
  Octi instead of to the right.
- **FR-027c (Must)** — The error screen's Octi plays `assets/logo/error/frame_*.txt` with the FR-030
  rules; given that folder is missing or empty, it plays the main logo frames (and, if those are
  missing too, the FR-032 fallback).
- **FR-029 (Must)** — Given `LANGSMITH_TRACING` is not `true`, Then the app still starts, and the
  sidebar's status button reads "Status: Not traced" (peach dot) and its modal says runs are not traced and how to turn tracing on (D-036, amending D-024) (D-024: offline tests need tracing
  off; normal use keeps it on, as assignment §3.3 requires).

### Logo animation
- **FR-030 (Must)** — Given `assets/logo/` contains files matching `frame_*.txt`, Then the logo plays
  them in ascending filename order in a loop at a code-constant speed (default 8 frames per second,
  D-020): complete text frames switch instantly with CSS visibility; movement is drawn inside the
  text files, with no transforms or fades (D-042). All frames share a fixed canvas; no Python loop
  or reruns. Ligatures are disabled so the drawing renders exactly as the text file.
  Reduced-motion users get the first frame, still.
- **FR-031 (Must)** — Given frame text containing `<`, `>`, `&` or quotes, Then it is displayed
  literally (escaped), never interpreted as HTML.
- **FR-032 (Must)** — Given `assets/logo/` is missing or has no frames, Then a plain "Octi" title is
  shown instead and no error is raised.
- **FR-033 (Must)** — The repo ships the student's Octi art (D-035): 8 main frames (mouth closed in
  all main frames, with movement only below row 26) and 8 error frames (closed/open pairs:
  Octi "talks" only next to the error speech bubble), per D-042.

### Tests and docs
- **FR-034 (Must)** — Given the default test command, Then all tests run with no network access and
  without loading the repository's `.env` (BR-009), using stubbed LLM, embeddings and Pinecone.
- **FR-035 (Must)** — Given the `live` marker is explicitly selected, Then one smoke test runs the
  service check (FR-015) against the real services using the developer's `.env` and expects no
  `FAIL` line. The script and the live test share one implementation, so they cannot disagree.
- **FR-036 (Must)** — The README contains the setup section of D-023, including the service check,
  the security notes of D-017, and a note that client retries are the OpenAI client's built-in ones
  (difference from the course labs, D-026).

## 5. Business Rules

- **BR-001** — All LLM and embedding calls go through the university LiteLLM proxy.
  *Rationale:* assignment §3.2. *Exceptions:* none; tests use stubs, not other providers.
- **BR-002** — Octi code reads configuration only from `Settings`, never from `os.environ` directly.
  *Rationale:* parse once at the boundary (D-013). *Exceptions:* LangChain/LangSmith libraries read
  their own variables from the environment (that is why `load_dotenv()` runs first).
- **BR-003** — No secret value ever appears in UI text, stdout of scripts, log lines, exception
  messages, prompts, graph state or traces. *Rationale:* assignment §11, CLAUDE.md. *Exceptions:*
  the three client factories unwrap secrets to construct clients, and the log redactor reads them to
  remove them from log text (FR-009). *Scope:* spec 00 verifies UI,
  script, log and exception output; the prompt, graph-state and trace parts get their VCs in specs
  01/02.
- **BR-004** — The app never creates, deletes or modifies the Pinecone index. *Rationale:* D-010.
  *Exceptions:* none; only the setup script creates it.
- **BR-005** — Index records live in namespace `PINECONE_NAMESPACE` (default `octi`).
  *Rationale:* D-014. *Exceptions:* none.
- **BR-006** — Client-level retries follow the OpenAI client's built-in policy (connection errors,
  timeouts, HTTP 408, 409, 429 and ≥ 500), with exponential backoff and jitter, 3 attempts in total
  by default (`LLM_MAX_RETRIES=2`; attempts = `LLM_MAX_RETRIES` + 1); other errors (e.g. 400, 401, 404) are not retried; Octi adds no retry
  loop of its own. *Rationale:* D-021, D-026, assignment §11 (no unbounded retry loops).
  This differs from the course labs' app-owned ladder (`max_retries=0`); with a single retry layer
  there is no double counting. *Exceptions:* none.
- **BR-007** — UI and script error text is the leaf error's `user_message`; raw exception text from
  third-party libraries is never shown. *Rationale:* D-027. *Exceptions:* none.
- **BR-011** — A new leaf error is added only when code or UI must react to it differently, or the
  message to the user differs; otherwise the closest existing leaf is reused. *Rationale:* keeps the
  hierarchy explicit without one class per error string (D-027). *Exceptions:* none.
- **BR-008** — One conversation per browser session; it lives only in session memory.
  *Rationale:* D-016, assignment §7 ("dentro de la sesión"). *Exceptions:* none.
- **BR-009** — The default test run never loads the repository-root `.env` and never sees real keys;
  every `Settings` used in tests is built from fake values (tests may load temporary fixture env files
  they create themselves). *Rationale:* CLAUDE.md (offline tests), D-017.
  *Exceptions:* tests explicitly marked `live` (FR-035).
- **BR-010** — Secrets are redacted from log text only when at least 8 characters long; FR-004a makes
  shorter secrets a configuration error. *Rationale:* replacing very short strings inside prose
  corrupts ordinary words (course lab `02-memory`, `MIN_REDACTABLE_KEY = 8`). *Exceptions:* none.

## 6. Non-Functional Requirements

- **NFR-001 (Performance)** — The offline test suite completes in under 30 s on the student's machine.
- **NFR-002 (Performance)** — The service-check script completes in under 60 s when all services are
  healthy (measured once by the student; a slow or failing service can take longer, bounded by the
  per-call timeouts and retries).
- **NFR-003 (Performance)** — With services reachable, the app's first screen renders in under 5 s
  after the browser connects.
- **NFR-004 (Reproducibility)** — Every dependency in `requirements.txt` is pinned with `==`; a fresh
  venv on Python 3.11+ installs it with one `pip install -r requirements.txt`.
- **NFR-005 (Security)** — Zero occurrences of any secret value in: test output, script output, log
  output, rendered UI text (verified with known fake secrets in tests).
- **NFR-006 (Offline)** — The default test run opens zero network connections.
- **NFR-007 (UI)** — The shell and the error screen render without horizontal scrolling at 1280×800
  and at 375 px width.

## 7. Data & Interfaces

### Environment variables (`.env.example`)

| Variable | Type after parsing | Required | Default | Rule |
|---|---|---|---|---|
| `LITELLM_BASE_URL` | URL ending in `/v1` | yes | — | http(s) URL (FR-003) |
| `LITELLM_API_KEY` | secret | yes | — | ≥ 8 chars |
| `LLM_MODEL` | str | yes | — | non-empty |
| `LLM_MODEL_CHOICES` | str | no | "" | comma-separated extra chat models for the picker (FR-024a) |
| `EMBEDDING_MODEL` | str | yes | — | non-empty |
| `EMBEDDING_DIMENSION` | int > 0 | no | 1536 | D-003 |
| `LLM_TEMPERATURE` | float 0–2 | no | 0 | D-021 |
| `LLM_TIMEOUT_SECONDS` | int > 0 | no | 60 | D-021 |
| `LLM_MAX_RETRIES` | int ≥ 0 | no | 2 | D-021 (3 attempts total) |
| `LANGSMITH_TRACING` | bool | no | true | FR-029 |
| `LANGSMITH_API_KEY` | secret | when tracing is on | — | ≥ 8 chars; optional when `LANGSMITH_TRACING=false` |
| `LANGSMITH_PROJECT` | str | no | `octi` | D-002 |
| `LANGSMITH_ENDPOINT` | URL | no | `https://api.smith.langchain.com` | http(s) URL |
| `LANGSMITH_WORKSPACE_ID` | str | no | empty | — |
| `PINECONE_API_KEY` | secret | yes | — | ≥ 8 chars |
| `PINECONE_INDEX_NAME` | str | no | `octi-tables` | lowercase letters, digits, `-`; 1–45 chars |
| `PINECONE_NAMESPACE` | str | no | `octi` | non-empty |
| `LOG_LEVEL` | log level | no | `INFO` | DEBUG/INFO/WARNING/ERROR |

### Public interfaces (consumed by specs 01/02)
- `get_settings() -> Settings` — built once per process; raises `InvalidSettingsError`.
- `make_chat_model(settings) -> BaseChatModel`, `make_embeddings(settings) -> Embeddings`.
- `check_index(settings) -> IndexStatus` with outcome `ok | missing | mismatch | unreachable`,
  expected/actual dimension and metric, and a safe reason.
- Error classes of D-027, importable from one module:

```
AppError                                     # .user_message
├── ConfigurationError
│   └── InvalidSettingsError 🍃              # .fields (names only)
└── ExternalServiceError                     # .service: "LiteLLM" | "Pinecone" | "LangSmith"
    ├── LLMProxyError
    │   ├── ProxyUnreachableError 🍃
    │   ├── ProxyAuthenticationError 🍃
    │   ├── ModelNotAvailableError 🍃
    │   └── EmbeddingDimensionError 🍃
    ├── VectorStoreError
    │   ├── VectorStoreUnreachableError 🍃
    │   ├── VectorStoreAuthenticationError 🍃
    │   └── IndexMismatchError 🍃            # .expected / .actual (dimension, metric)
    └── TracingError
        ├── TracingUnreachableError 🍃
        └── TracingAuthenticationError 🍃
```
🍃 = leaf, what Octi code raises; the others are groups for `except`.
- `configure_logging(settings)`.

### Files
- `assets/logo/frame_*.txt` — UTF-8 text, one frame per file.
- `assets/logo/error/frame_*.txt` — UTF-8 text, error-screen frames (optional; FR-027c).
- `.streamlit/config.toml` — Catppuccin Mocha theme (FR-019a).

### Code constants (not configuration)
- Pinecone location for index creation: cloud `aws`, region `us-east-1` (free plan).
- Logo speed: 8 frames per second (D-020).
- Speech bubble width: 48 characters (D-032).
- Catppuccin Mocha colors listed in FR-019a (D-029).

## 8. Verification Criteria

Configuration
- VC-001 (FR-001): environment with all required variables → `get_settings()` returns `Settings`
  with typed values; two calls return the same object.
- VC-002 (FR-001): shell variable `LLM_MODEL=a` and `.env` `LLM_MODEL=b` → `Settings.LLM_MODEL == "a"`.
- VC-003 (FR-002): `LITELLM_API_KEY` and `LLM_MODEL` missing → `InvalidSettingsError` whose message contains
  both names and does not contain any other variable's value.
- VC-004 (FR-002): `PINECONE_INDEX_NAME="Octi_Tables"` → `InvalidSettingsError` naming `PINECONE_INDEX_NAME`.
- VC-005 (FR-002): `LLM_TIMEOUT_SECONDS="0"` and `LLM_TEMPERATURE="3"` → `InvalidSettingsError` naming both.
- VC-006 (FR-003): base URLs `https://p.x`, `https://p.x/`, `https://p.x/v1`, `https://p.x/v1/` →
  each parses to `https://p.x/v1`.
- VC-007 (FR-004): `Settings` with fake key `sk-FAKE-123` → `str()`, `repr()` and a raised exception
  containing it do not include `sk-FAKE-123`.
- VC-007a (FR-004a): `PINECONE_API_KEY="abc"` → `InvalidSettingsError` naming `PINECONE_API_KEY`.
- VC-007b (FR-002, Data): `LANGSMITH_TRACING=false` and no `LANGSMITH_API_KEY` → `Settings` builds;
  `LANGSMITH_TRACING=true` and no key → `InvalidSettingsError` naming `LANGSMITH_API_KEY`.
- VC-007c (BR-002): a static scan of Octi's own modules finds `os.environ` / `os.getenv` only inside
  the settings module.
- VC-007d (BR-005): no `PINECONE_NAMESPACE` → `Settings.PINECONE_NAMESPACE == "octi"`; set to `x` → `"x"`.

Model factories
- VC-008 (FR-005): factory output → base URL, model name, temperature 0, timeout 60, max retries 2
  match `Settings` (inspected on the object, no network).
- VC-009 (FR-006): factory output → base URL, model name match `Settings`; client-side tokenization
  disabled.
- VC-010 (BR-001): every model object produced by the factories points at `LITELLM_BASE_URL`.
- VC-010a (BR-006): both factory outputs are configured with the retry count and timeout from
  `Settings` (default: 2 retries = 3 attempts, 60 s), and no Octi code adds a second retry loop around
  them.

Errors and logging
- VC-011 (FR-007, BR-011): every class in the §7 tree exists with the parent shown; every leaf has a
  non-empty `user_message`; every `ExternalServiceError` leaf reports its `service`. BR-011 is checked
  by review: each leaf has its own message or a distinct reaction in the code.
- VC-012 (FR-008): in the setup script, a stubbed Pinecone client raising a connection error →
  `VectorStoreUnreachableError` with the original exception as `__cause__`; raising an authentication
  error → `VectorStoreAuthenticationError`; existing index with dimension 3072 → `IndexMismatchError`
  with expected 1536 / actual 3072.
- VC-012a (FR-008): in the service check, a chat stub raising a connection error →
  `ProxyUnreachableError` (shown as the chat `FAIL` reason via `user_message`); a 401 →
  `ProxyAuthenticationError`.
- VC-013 (FR-009, NFR-005): log a message containing `sk-FAKE-12345` (a configured secret) → captured
  output contains `***` and not `sk-FAKE-12345`.
- VC-013a (BR-010): configured secrets of length ≥ 8 → the word "leveraging" in a log line is left
  intact.
- VC-014 (FR-010): `LOG_LEVEL=DEBUG` → root level DEBUG; unset → INFO.

Pinecone index (stubbed Pinecone client)
- VC-015 (FR-011): no index → setup creates one with dimension 1536, cosine, `aws/us-east-1`;
  output says "created".
- VC-016 (FR-012): matching index exists → no create/delete call; output says "already exists";
  exit 0.
- VC-017 (FR-013): index with dimension 3072 → no create/delete call; exit non-zero; output shows
  "expected 1536, actual 3072".
- VC-018 (FR-014, BR-004): `check_index` on missing / matching / mismatched index → `missing` /
  `ok` / `mismatch`; the stub records zero create/delete/configure calls.
- VC-018a (FR-014): Pinecone stub raising a connection error, and separately an authentication error →
  `unreachable` with a safe reason containing no key material.

Service check (stubbed services)
- VC-019 (FR-015): all stubs healthy → six `OK` lines (configuration, models, chat, embeddings,
  Pinecone, LangSmith); exit 0.
- VC-019a (FR-015): proxy model list lacking `LLM_MODEL` → models line `FAIL` naming the missing id.
- VC-020 (FR-015): embeddings stub returns a 3072-length vector → embeddings line `FAIL` mentioning
  expected 1536.
- VC-021 (FR-016): `.env` reported as tracked by git → a `FAIL` line telling the user to untrack it.
- VC-021a (FR-016): folder is not a git repository → `skipped (not a git repository)`; exit code
  unaffected by this line.
- VC-022 (FR-017): chat stub raises → chat `FAIL`, the other checks still reported; exit non-zero.
- VC-022a (FR-017): building the LangSmith client raises → only the `langsmith` line fails; the chat,
  embeddings and Pinecone stubs still record their calls and report `OK`.
- VC-023 (FR-018): invalid configuration → configuration `FAIL` naming fields; service checks
  reported as skipped; exit non-zero.
- VC-024 (BR-003, BR-007): any stub raising an exception whose text contains `sk-FAKE-123` → script
  output does not contain `sk-FAKE-123`.

Streamlit shell (Streamlit `AppTest`, services stubbed)
- VC-025 (FR-019): app opens → sidebar buttons "Octi", "New chat" (with shortcut), "Library"; the
  Documents section with "No documents yet"; the status popover holding the three status items and
  the embedding model; view `Chat`; Library then "Octi" → back to Chat with the messages kept; no
  emoji in the UI code (D-036);
- VC-025b (FR-026a): 5 tables → 3 shown + "View all"; 7 PDFs → 5 shown + "Show more"; names escaped;
- VC-025a (FR-024a): `LLM_MODEL_CHOICES="model-b, <LLM_MODEL>, model-c"` → picker options
  `[LLM_MODEL, model-b, model-c]`, default `LLM_MODEL`; pick `model-b`, send a message → still `model-b`; the LiteLLM stub records zero calls.
- VC-026 (FR-020): empty conversation → logo, greeting and composer present in that order, the
  composer rendered inline (not pinned).
- VC-026a (FR-019a): `.streamlit/config.toml` sets background `#1e1e2e`, secondary background
  `#181825`, text `#cdd6f4`, primary `#cdd6f4` (neutral controls, D-042); base and button radius
  `0.75rem`.
- VC-027 (FR-021, FR-022): submit "hello" → logo and greeting absent; composer pinned (top-level);
  history shows user "hello" then the assistant placeholder mentioning spec 02.
- VC-028 (FR-023): attach `report.pdf` → user message shows `report.pdf`; assistant placeholder
  mentions spec 01; nothing written to disk.
- VC-028a (FR-023a): submit "what is this?" with `report.pdf` → one user message with both; assistant
  reply contains the spec-01 then the spec-02 placeholder.
- VC-029 (FR-024): composer configuration accepts only the `pdf` file type.
- VC-030 (FR-025, FR-025a): two messages, click "New chat" → modal with Erase, Cancel and the
  checkbox; click Cancel → two messages remain; click "New chat" then Erase → history empty, logo
  present.
- VC-030a (FR-025a, FR-025b): two messages, "New chat", tick checkbox, Erase; add a message; "New
  chat" → cleared immediately, no modal.
- VC-030b (FR-025a): tick checkbox then Cancel; "New chat" again → modal still appears.
- VC-030c (FR-025c): empty conversation, "New chat" → no modal.
- VC-030d (FR-025b): a new `AppTest` session (refresh) after disabling warnings → modal appears again.
- VC-031 (FR-026): click the sidebar's "Library" row → empty-state message present; the row is highlighted.
- VC-032 (FR-027, FR-027a): invalid configuration (`LITELLM_API_KEY` missing) → error screen: Octi
  plus a bubble naming `LITELLM_API_KEY`, the `.env.example` instruction and the README section; no
  exception escapes; no sidebar/composer rendered.
- VC-033 (FR-028): index status `missing` → error screen with the setup command; `mismatch` → expected
  vs actual; `unreachable` → network / `PINECONE_API_KEY` hint; no shell rendered in any case.
- VC-033a (FR-027a): every bubble line is ≤ 48 characters plus frame; the bubble starts with `╭` and
  ends with `╯`; a reason containing `sk-FAKE-12345` → absent from the rendered screen.
- VC-033b (FR-027c): error frames present → they are played; error folder empty → main frames
  played; both empty → plain "Octi" title.
- VC-034 (FR-029): `LANGSMITH_TRACING=false` → status button reads "Status: Not traced"; its popover states
  that runs are not traced and names `LANGSMITH_TRACING=true`.
- VC-035 (BR-008): two independent `AppTest` sessions → a message in one does not appear in the other.

Logo
- VC-036 (FR-030): frames `frame_02.txt`, `frame_01.txt`, `frame_10.txt` → rendered order 01, 02, 10;
  rendered HTML contains one CSS animation whose total duration is 3 frames ÷ 8 fps = 0.375 s; rows
  above 26 stay fixed in the shipped idle frames, while tentacles change within the text.
- VC-037 (FR-031): frame containing `<script>&"` → rendered HTML contains the escaped entities and no
  `<script>` element.
- VC-038 (FR-032): empty or missing folder → plain "Octi" title; no exception.
- VC-039 (FR-033): repo contains 8 `assets/logo/frame_*.txt` with an unchanged closed mouth
  and distinct tentacles, and 8 `assets/logo/error/frame_*.txt` with two mouth poses.

Tests and docs
- VC-040 (FR-034, NFR-001, NFR-006): default `pytest` with network disabled → all pass, zero network
  connections, under 30 s.
- VC-040a (BR-009): during the default test run, any attempt to load the repository-root `.env` fails
  the run (guard active for every test), while loading a temporary fixture env file succeeds; the
  `Settings` objects used contain only fake values.
- VC-041 (FR-035): `pytest -m live` with a valid `.env` → the live service-check test reports no
  `FAIL` line (manual, by the student).
- VC-042 (FR-036, NFR-004): README contains, in order: purpose, prerequisites, venv + install,
  `.env` setup with security notes, index setup, service check, tests, run the app (no page map:
  D-043); every line of `requirements.txt` uses `==`.
- VC-043 (NFR-002, NFR-003, NFR-007, FR-019a, FR-020, FR-021, FR-027b): end-to-end manual check by the student: service check under
  60 s; first screen under 5 s; no horizontal scroll at 1280×800 and 375 px; in the empty state the
  logo, greeting and composer are centered (FR-020); the composer moves to the bottom after the
  first message (FR-021); the error screen stacks the bubble below Octi at 375 px (FR-027b); the
  colors match Catppuccin Mocha (FR-019a).

## 9. Open Questions

None.

## 10. Assumptions

- **A-003** — Streamlit 1.65's `st.chat_input(accept_file=True, file_type=["pdf"])` provides the
  composer's "+".
- **A-004** — `requirements.txt` pins only what spec 00 uses, at the versions working in the student's
  playground venv: langchain-core 1.6.6, langchain-openai 1.6.7, langsmith 0.14.4, pinecone 10.0.0,
  pydantic 2.13.5, python-dotenv 1.2.4, streamlit 1.65.0, plus pytest. LangGraph, pandas and PyMuPDF
  are added by spec 01/02 when first used.
- **A-005** — The proxy accepts plain-string embedding inputs (verified in playground lessons 05–06).
- **A-006** — `Settings` defaults are not written back to the environment, while LangChain/LangSmith
  read tracing variables (`LANGSMITH_TRACING`, `LANGSMITH_PROJECT`, …) from the environment
  themselves. Spec 00 relies on `.env.example` setting them explicitly; specs 01/02 must make sure
  an omitted variable still yields a traced run (e.g. explicit tracing setup at the graph boundary).
