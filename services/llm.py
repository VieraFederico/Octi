"""Factories for the models behind the university LiteLLM proxy (BR-001).

Every chat and embedding call in Octi uses an object built here, so the proxy URL, model names,
timeout and retry policy are set in exactly one place. The proxy speaks the OpenAI API, which is why
`langchain_openai` is used even though the models behind it may come from other vendors.

Retries: the OpenAI client already retries connection errors, timeouts, 408, 409, 429 and >= 500 with
exponential backoff and jitter. `max_retries=2` means 3 attempts in total (D-021). Octi adds no retry
loop of its own (BR-006, D-026), so the factories return the LangChain objects as they are.

The API key is passed as the `SecretStr` from `Settings`: LangChain keeps it masked, so Octi never
unwraps it here. Factory idea adapted from the course's Lab 01 (Knowledge) — see README › Credits.
"""

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from services.settings import Settings


def make_chat_model(settings: Settings) -> ChatOpenAI:
    """A chat model on the proxy, configured entirely from `settings` (FR-005)."""
    return ChatOpenAI(
        base_url=settings.LITELLM_BASE_URL,
        api_key=settings.LITELLM_API_KEY,
        model=settings.LLM_MODEL,
        temperature=settings.LLM_TEMPERATURE,
        timeout=settings.LLM_TIMEOUT_SECONDS,
        max_retries=settings.LLM_MAX_RETRIES,
    )


def make_embeddings(settings: Settings) -> OpenAIEmbeddings:
    """An embedding model on the proxy, with the same timeout and retry policy (FR-006)."""
    return OpenAIEmbeddings(
        base_url=settings.LITELLM_BASE_URL,
        api_key=settings.LITELLM_API_KEY,
        model=settings.EMBEDDING_MODEL,
        # LangChain normally turns text into OpenAI token ids before sending it. The proxy may route
        # to a non-OpenAI model that expects plain strings, so that step is switched off.
        check_embedding_ctx_length=False,
        timeout=settings.LLM_TIMEOUT_SECONDS,
        max_retries=settings.LLM_MAX_RETRIES,
    )
