# Octi

Octi answers questions about the tables inside PDF reports. An **Ingestion agent** extracts each
table, describes it with an LLM and indexes it in Pinecone; an **Analyst agent** finds the tables a
question needs, writes and runs Python to compute the answer, and says whether the question was
`answered`, `partial` or `cannot_answer`.

> Work in progress: the foundation (configuration, service clients, setup and diagnostics) is in
> place; the agents and the Streamlit app are being built. This README grows with them.

## Getting started

**Prerequisites:** Python 3.11+, a key for the university LiteLLM proxy (sent on the course
channel), a free [Pinecone](https://www.pinecone.io/) account and a free
[LangSmith](https://smith.langchain.com/) account.

1. **Create a virtual environment and install the dependencies** (from the repository root):
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. **Configure your secrets:** copy `.env.example` to `.env` and fill it in. `.env` is git-ignored:
   never commit it. Every variable is explained in `.env.example`.
3. **Create the Pinecone index** (safe to run again; it never deletes anything):
   ```bash
   python -m scripts.setup_index
   ```
4. **Check every service:** one line per check, `OK` or `FAIL: <what to do>`; exit code 0 means
   everything works.
   ```bash
   python -m scripts.check_services
   ```
5. **Run the tests** (offline: no network, no real keys):
   ```bash
   pytest
   ```

## Credits

Ideas and patterns adapted from the course material of *Sistemas Multiagente I* (cátedra, ITBA):

- **Laboratorio 01 — Knowledge:** a single factory function for the proxy-backed chat model.
- **Laboratorio 02 — Memory:** a minimum secret length (8 characters) for redacting keys from log text.
- **Notebook "01 — Demo LiteLLM":** asking the proxy for its model list before the first call.
