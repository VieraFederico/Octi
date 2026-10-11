# Frozen: Spec 00 — Foundation

Source: `specs/00-foundation.md` (v0.7)
Status: SHIPPED (`/verify-spec` PASSED 2026-10-10)
Frozen: 2026-10-11
PR / commit: no PR (student commits on `main`): `6a462a5`, `4cd063a`, `e459ca1`, `b052517`,
`b220669`, `705105a`, `25602ae`, `74e6781`
Decisions: root `DECISIONS.md` D-001 … D-045; spec-local `S00-D-NNN` in
`specs/00-foundation-plan-artifacts/DECISIONS.md`. Glossary: `CONTEXT.md`.

## Purpose
Octi answers questions about tables inside machine-readable PDFs with two LangGraph agents
(assignment §1). Before either agent exists, the project needs a foundation every later spec builds
on: a reproducible setup, typed and safe configuration, factories for the university LiteLLM proxy,
tracing, the Pinecone index, an explicit error vocabulary, an offline test harness, a way to prove
all external services work, and the chat-first Streamlit shell the agents will plug into. This spec
delivers exactly that and nothing agent-specific. It benefits the student (a working, explainable
base before the deadline) and the graders (a setup they can reproduce and verify in minutes).

## What it does

Configuration
- Loads the repository-root `.env` (located from the code, never overriding shell variables) and
  builds one typed `Settings` per process; secrets are `SecretStr`, masked in every print, log and
  exception, and must be at least 8 characters (FR-001 … FR-004a).
- Missing or invalid variables raise `InvalidSettingsError` naming the variables, never their values;
  `LITELLM_BASE_URL` is normalized to end in exactly one `/v1` (FR-002, FR-003).
- Octi code reads configuration only through `Settings`, never `os.environ` (BR-002); no secret ever
  reaches UI text, script output, logs or exceptions (BR-003; prompts, graph state and traces are
  verified by spec 01).

Models, errors and logging
- `make_chat_model` and `make_embeddings` build LangChain models on the proxy from `Settings`
  (model, temperature, timeout, retries; embeddings as plain strings) (FR-005, FR-006).
- Every LLM and embedding call goes through the LiteLLM proxy (BR-001). Retries are the OpenAI
  client's built-in ones only (connection errors, timeouts, 408/409/429/≥500; 3 attempts by
  default); Octi adds no retry loop (BR-006).
- External-client failures are re-raised as the matching leaf error of the D-027 tree with the cause
  chained; a missing index is a status, not an error (FR-007, FR-008). A new leaf is added only when
  code or UI must react differently (BR-011). UI and script text is the leaf's `user_message`, never
  raw library text (BR-007).
- Octi's log handler replaces secret values with `***`; level from `LOG_LEVEL`, default `INFO`
  (FR-009, FR-010, BR-010).

Pinecone index and service check
- `scripts/setup_index.py` creates the serverless index (dimension `EMBEDDING_DIMENSION`, cosine,
  `aws/us-east-1`) or leaves a matching one untouched; a mismatched one exits non-zero showing
  expected vs actual (FR-011 … FR-013). The app never creates, deletes or modifies the index (BR-004).
- At startup `check_index` reports `ok`, `missing`, `mismatch` or `unreachable` with a safe reason
  (FR-014). Index records live in namespace `PINECONE_NAMESPACE`, default `octi` (BR-005).
- The service-check script prints one `OK` / `FAIL: <reason>` line each for configuration, proxy
  models, chat, embeddings (dimension), Pinecone, LangSmith and a git-tracked secrets file; every
  check runs independently; the exit code is non-zero on any failure (FR-015 … FR-018).

Streamlit shell
- A chat-first single page: sidebar with the "Octi" wordmark (back to chat), "New chat"
  (Cmd/Ctrl+Shift+O), "Library", a Documents preview (5 PDFs / 3 table names, native in-place
  expanders) and a status button whose popover shows configuration, index status, tracing and the
  embedding model; no emojis, SVG icons; no LiteLLM call at startup (FR-019, FR-026a).
- Empty chat: centered animated ASCII logo, greeting and inline composer; after the first message
  the history shows and the composer pins to the bottom (FR-020, FR-021). Catppuccin Mocha palette
  with neutral `#cdd6f4` controls (FR-019a).
- The composer accepts text and PDFs only ("+"); replies are placeholders until specs 01/02; a
  chat-model picker (`LLM_MODEL` first, then `LLM_MODEL_CHOICES`, not typeable) holds the session's
  choice for the Analyst; the embedding model is not selectable (FR-022 … FR-024a).
- "New chat" asks before erasing a non-empty conversation (Erase / Cancel / "Don't warn me again"
  for the session) and always shows the Chat view (FR-025 … FR-025c). One conversation per browser
  session, in session memory only (BR-008).
- The Library view shows an empty state until spec 01 (FR-026).
- Invalid configuration or a non-`ok` index shows the Octi error screen instead of the shell: the
  animated Octi plus an ASCII speech bubble (≤ 48 characters per line) saying what failed, what to
  do and which README section to read, stacking below Octi under 900 px; never secrets or raw
  library text (FR-027 … FR-028). Tracing off keeps the app running with "Status: Not traced"
  (FR-029).
- The logo plays `assets/logo/frame_*.txt` in filename order at 8 fps with CSS only, escaped
  literally, falling back to a plain "Octi" title; the repo ships 8 main and 8 error frames
  (FR-030 … FR-033).

Tests and docs
- The default `pytest` run is offline: stubbed LLM, embeddings and Pinecone, the repository secrets
  file never loaded, fake secrets only; the `live` marker runs the service check against the real
  services (FR-034, FR-035, BR-009).
- The README has the setup section (prerequisites, venv + install, secrets with security notes,
  index setup, service check, tests, run) and states the built-in retry policy (FR-036).

## Public interfaces / data

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

## Key decisions
- Plain Pydantic `Settings` after `load_dotenv()` (D-013): `pydantic-settings` does not populate
  `os.environ`, which would silently turn LangSmith tracing off.
- The OpenAI client's built-in retries instead of the course labs' app-owned ladder (D-021, D-026):
  zero code and one retry layer, so attempts are never double counted; wrong answers are retried by
  the graphs, not the client.
- An explicit error tree with group bases and leaves (D-027, BR-011): callers catch families, code
  raises leaves with user-safe messages, without one class per error string.
- The index is created only by a setup script; the app only checks it (D-010, BR-004): creation is
  setup, and a dimension mismatch is caught before the first upsert.
- Startup makes no LiteLLM call; the full service check lives in a script (D-025): Streamlit reruns
  often and the check costs proxy calls.
- Tracing off is allowed with a visible warning (D-024): offline tests need it off; normal use keeps
  it on, as the assignment requires.
- Chat-first single page with Library and Documents in the sidebar (D-016, D-036, D-040), and a full
  error screen for configuration and index problems (D-031, D-032): one place to work, problems
  explained in plain words with the README section to read.
- Logo frames are whole text files switched by CSS visibility (D-020, D-042): no Python loop or
  reruns; reduced-motion users get one still frame.
- Secrets are redacted only when at least 8 characters long (BR-010): replacing very short strings
  corrupts ordinary words (course memory lab).
- README in product style with no page map (D-043); `.gitattributes` forces LF line endings (D-044).

## Known limits (still true at freeze)
- Offline suite under 30 s (NFR-001; spec 01 raises it to 60 s, D-075); the default test run opens no
  network connection (NFR-006).
- Service check under 60 s when healthy (NFR-002); first screen under 5 s (NFR-003); no horizontal
  scroll at 1280×800 and 375 px (NFR-007).
- Every dependency pinned with `==` (NFR-004); zero secret occurrences in test, script, log and UI
  output (NFR-005).
- `Settings` defaults are not written back to the environment, while LangChain/LangSmith read the
  tracing variables from it (A-006); spec 01 keeps runs traced when they are omitted (spec 01
  FR-154).
- Spec 01 replaces the PDF placeholder (FR-023, half of FR-023a) and fills the Library and the
  Documents preview (FR-026, FR-026a).

## Deliberately excluded
- Agents, Table store, PDF extraction, sandbox, answerability and agent retry limits (specs 01/02);
  evaluation, diagrams and bonus features (spec 03).
- Persistent or multiple conversations, authentication, deployment, and any change that makes the
  secrets file readable to Claude.
