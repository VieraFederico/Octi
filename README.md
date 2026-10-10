<p align="center">
  <img src="assets/readme-head.svg" alt="The top of Octi's head, including his eyes" width="400">
</p>

<h1 align="center">Hi, I'm Octi!</h1>

Octi answers questions about the tables inside PDF reports. An **Ingestion agent** extracts each
table, describes it with an LLM and indexes it in Pinecone; an **Analyst agent** finds the tables a
question needs, writes and runs Python to compute the answer, and says whether the question was
`answered`, `partial` or `cannot_answer`.

> **Status: foundation.** What works today: typed configuration, the clients for the LiteLLM
> proxy, Pinecone and LangSmith, the Pinecone index setup, a service check, an offline test
> suite, and the Streamlit app shell (chat, library, "New chat", error screen). The two agents are
> not built yet: the app answers with placeholders until they arrive.

## Getting started

### Prerequisites

- Python 3.11 or newer (developed on 3.13).
- A key for LiteLLM proxy and its base URL.
- A [Pinecone](https://www.pinecone.io/) account (API key).
- A [LangSmith](https://smith.langchain.com/) account (API key), for tracing.

Run every command below from the repository root.

### 1. Create a virtual environment and install the dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Every dependency is pinned with `==`, so a fresh environment installs the same versions.

### 2. Configure your secrets

```bash
cp .env.example .env
```

Fill in `.env`. `.env.example` lists every variable with a comment; the required ones are
`LITELLM_BASE_URL`, `LITELLM_API_KEY`, `LLM_MODEL`, `EMBEDDING_MODEL`, `LANGSMITH_API_KEY` (while
tracing is on) and `PINECONE_API_KEY`. The optional ones (timeouts, retries, temperature, index
name, namespace, log level) have working defaults and stay commented out.

Security notes:

- `.env` is already listed in the repository's `.gitignore`, so git leaves it out of commits.
- Recommended on Linux and macOS: `chmod 600 .env`, so only your user can read it.
- The service check (step 4) fails with a clear message if git ever tracks `.env`.
- Octi never shows a key: configuration errors name the variable, never its value; log lines have
  every configured secret replaced by `***`; the app and the scripts show only messages Octi wrote,
  never raw text from a library or the proxy.
- A value left empty (`KEY=`) counts as missing.

### 3. Create the Pinecone index

```bash
python -m scripts.setup_index
```

Creates the Pinecone index named by `PINECONE_INDEX_NAME` (default `octi-tables`), with
`EMBEDDING_DIMENSION` dimensions (default 1536) and the cosine metric. Safe to run again: it never
deletes or changes an index. An index you already have works too, as long as its name, dimension
and metric match. The app never creates the index; it only checks it.

### 4. Check every service

```bash
python -m scripts.check_services
```

One line per check, in this order: configuration, models, chat, embeddings, pinecone, langsmith,
git. Each line reads `OK`, `FAIL: <what to do>` or `skipped (<why>)`. Exit code 0 means nothing
failed. It makes one real chat call and one real embedding call (a little of your proxy budget), and
takes under a minute when every service is healthy. Run it first whenever something does not work.

```text
configuration: OK
models: OK
chat: OK
embeddings: OK
pinecone: OK
langsmith: OK
git: OK
```

### 5. Run the tests

```bash
pytest            # offline: about 190 tests in under 30 s
pytest -m live    # one smoke test against the real services, with your .env
```

The default run is offline by construction: a guard fails any test that opens a network
connection, another fails any test that loads the real `.env`, and every model, embedding,
Pinecone and LangSmith client is a stub with fake keys. Tests check that those fake keys never
appear in any output. The live test runs the same code as the service check, so the two cannot
disagree.

### 6. Run the app

```bash
streamlit run app.py
```

At start-up the app checks the configuration and the Pinecone index once (no LLM call, so opening
the app costs nothing). If something is wrong, Octi's error screen says what failed, what to do,
and which section of this README to read. The check runs once per server process: after you fix
`.env` or create the index, **restart** the app.

## Project architecture

```text
Octi/
├── app.py                   Streamlit entry point: start-up check, then sidebar + current view
├── requirements.txt         pinned dependencies
├── pytest.ini               test settings (live tests excluded by default)
├── .env.example             every configuration variable, with comments
├── .streamlit/
│   └── config.toml          theme (Catppuccin Mocha) and fonts
├── assets/
│   ├── styles.css           global stylesheet (palette as CSS variables)
│   ├── octi.svg             browser-tab icon
│   ├── readme-head.svg      README header image
│   └── logo/
│       ├── frame_*.txt      animated ASCII logo, one frame per file
│       └── error/
│           └── frame_*.txt  error-screen logo frames
├── services/                back end, one module per concern (no Streamlit)
│   ├── settings.py          configuration: .env → typed Settings (the only reader of the environment)
│   ├── errors.py            error tree
│   ├── logging_setup.py     logging with secret redaction
│   ├── llm.py               LiteLLM proxy: chat and embedding clients, error translation
│   ├── vector_store.py      Pinecone: index check (read-only) and index creation
│   ├── tracing.py           LangSmith: client and error translation
│   └── health.py            service check, shared by the script and the live test
├── scripts/
│   ├── setup_index.py       creates the Pinecone index
│   └── check_services.py    checks every service, one line each
├── ui/                      the Streamlit app
│   ├── startup.py           start-up check (configuration + index), cached per process
│   ├── sidebar.py           wordmark, New chat, Library, Documents, status button
│   ├── chat.py              Chat view: empty state, history, composer, model picker
│   ├── library.py           Library view
│   ├── documents.py         sidebar Documents list
│   ├── new_chat.py          "New chat" confirmation modal
│   ├── error_screen.py      error screen and its messages
│   ├── bubble.py            ASCII speech bubble of the error screen
│   ├── logo.py              animated ASCII logo
│   ├── icons.py             SVG icons
│   └── style.py             loads assets/styles.css
├── tests/
│   ├── conftest.py          offline guards (no network, no real .env) and fixtures
│   ├── stubs.py             fake keys and stand-in clients
│   ├── unit/                one test file per module
│   ├── functional/          the app, driven by Streamlit's AppTest
│   └── live/                smoke test against the real services (pytest -m live)
├── DECISIONS.md             design decisions, with the alternatives considered
└── CONTEXT.md               glossary of the project's terms
```

## Design decisions

The full log, with the alternatives considered, is in [`DECISIONS.md`](DECISIONS.md).

### Configuration

- `load_dotenv()` copies `.env` into the process environment, so LangChain and LangSmith see their
  own variables.
- One Pydantic model, `Settings`, then parses and validates every variable once, at start-up.
- Keys are `SecretStr`: printing one shows `**********`.
- Any invalid variable stops start-up with one error that names every bad variable, never a value.
- Only `services/settings.py` reads the environment (a test enforces it).

### Errors

- `services/errors.py` defines a small tree:
  - group classes (`ConfigurationError`, `LLMProxyError`, `VectorStoreError`, `TracingError`, …) to
    catch a whole family;
  - leaves (`ProxyUnreachableError`, `IndexMismatchError`, …), the only classes the code raises.
- Each leaf carries a `user_message` that is safe to show.
- The original library exception is chained (`raise … from`) for the logs.
- Each service module translates its library's exceptions, so the rest of the code never sees a raw
  Pinecone or OpenAI error.

### Model calls and retries

- Every chat and embedding call goes through the LiteLLM proxy at `LITELLM_BASE_URL`, with
  `langchain_openai`.
- Defaults: temperature 0, 60 s timeout, `max_retries=2` (3 attempts in total).
- Retries are the OpenAI client's **built-in** ones:
  - exponential backoff with jitter;
  - only for connection errors, timeouts and HTTP 408, 409, 429 and 5xx;
  - a wrong key (401) or a bad request (400) fails at once.
- Why: the *Sistemas Multiagente I* course labs set `max_retries=0` and run their own retry ladder.
  Octi keeps a single retry layer, so attempts are never multiplied, and adds no loop of its own.
- Use short model ids (`gpt-5-mini`): LangChain drops `temperature` only for ids that start with
  `gpt-5`, and those models reject any temperature but the default.

### Pinecone index

- Created only by the setup script (or by you in Pinecone); the app never creates it.
- The app and the service check only read it, and report `ok`, `missing`, `mismatch` (wrong
  dimension or metric) or `unreachable`.
- Any status other than `ok` opens the error screen instead of the app.
- Every record lives in the namespace `PINECONE_NAMESPACE` (default `octi`), so the data can be
  wiped without touching the index.

### Tracing

- With `LANGSMITH_TRACING=true` (the default in `.env.example`), every agent run will be traced in
  the LangSmith project `LANGSMITH_PROJECT`.
- Tracing off is allowed, for example for offline work:
  - the app still opens, and its status button reads "Not traced";
  - the service check marks LangSmith as `FAIL`, because the assignment requires traced runs.

### Logging

- Standard `logging` to stderr, at `LOG_LEVEL` (default `INFO`).
- Octi's handler replaces every configured secret with `***`, tracebacks included.
- `LOG_LEVEL=DEBUG` shows the chained library errors behind a `FAIL` line.

### The app

- Streamlit reruns `app.py` on every interaction, so:
  - the start-up check (configuration + index) runs once per server process (`st.cache_resource`);
  - everything else is drawn from session state.
- One conversation per browser session; it disappears with the tab.
- "New chat" asks before erasing; "Don't warn me again" lasts for that session only.
- Theme: Catppuccin Mocha. Streamlit's widgets read it from `.streamlit/config.toml`;
  `assets/styles.css` repeats the palette as CSS variables for everything else.
- SVG icons only, no emojis.

## Credits

Ideas and patterns adapted from the course material of *Sistemas Multiagente I* (cátedra, ITBA):

- **Laboratorio 01 — Knowledge:** a single factory function for the proxy-backed chat model.
- **Laboratorio 02 — Memory:** a minimum secret length (8 characters) for redacting keys from log text.
- **Notebook "01 — Demo LiteLLM":** asking the proxy for its model list before the first call.

Other sources:

- [Catppuccin](https://catppuccin.com/palette) — the Mocha color palette (MIT license).
- [Inter](https://rsms.me/inter/) and [JetBrains Mono](https://www.jetbrains.com/lp/mono/) — fonts,
  served by Google Fonts (SIL Open Font License).
- [Streamlit documentation](https://docs.streamlit.io/) — the `st.dialog`, `st.cache_resource` and
  `AppTest` patterns used by the app and its tests.
- Octi's ASCII art is the author's own drawing.
