"""Configuration: load `.env`, then parse the environment once into a typed `Settings` object.

"Parse, don't validate" (decision D-013): raw strings from the environment are turned into typed,
checked values at this single boundary. The rest of Octi receives a `Settings` object and never reads
`os.environ` itself (BR-002) — this module is the only one that does.

`load_dotenv` puts the values into `os.environ` so LangChain/LangSmith, which read their own
variables from the environment, see them too. That is why plain Pydantic is used instead of
`pydantic-settings`, which would parse `.env` without populating `os.environ` (D-013).
"""

import os
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from dotenv import load_dotenv
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeInt,
    PositiveInt,
    SecretStr,
    ValidationError,
    ValidationInfo,
    field_validator,
)

from services.errors import InvalidSettingsError

# Resolved from this file's location, never from the current working directory (FR-001).
REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / ".env"

# A secret shorter than this cannot be redacted from log text without corrupting ordinary words
# (BR-010). Idea adapted from the course's Lab 02 (Memory) — see README › Credits.
MIN_SECRET_LENGTH = 8

SECRET_FIELDS = ("LITELLM_API_KEY", "PINECONE_API_KEY", "LANGSMITH_API_KEY")


def load_environment(env_file: Path | None = None) -> bool:
    """Load the repo-root `.env` into `os.environ`, never overriding variables set in the shell."""
    return load_dotenv(env_file if env_file is not None else ENV_FILE, override=False)


def _check_http_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("must be an http(s) URL")
    return value


def _check_secret_length(value: SecretStr | None) -> SecretStr | None:
    if value is not None and len(value.get_secret_value()) < MIN_SECRET_LENGTH:
        raise ValueError(f"must be at least {MIN_SECRET_LENGTH} characters")
    return value


class Settings(BaseModel):
    """Every value Octi reads from the environment, already typed and checked (spec §7)."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    # LiteLLM proxy (all LLM and embedding calls go through it — BR-001)
    LITELLM_BASE_URL: str
    LITELLM_API_KEY: SecretStr
    LLM_MODEL: str = Field(min_length=1)
    LLM_MODEL_CHOICES: str = ""  # comma-separated extra models for the composer's picker (D-037)
    EMBEDDING_MODEL: str = Field(min_length=1)
    EMBEDDING_DIMENSION: PositiveInt = 1536
    LLM_TEMPERATURE: float = Field(default=0.0, ge=0.0, le=2.0)
    LLM_TIMEOUT_SECONDS: PositiveInt = 60
    LLM_MAX_RETRIES: NonNegativeInt = 2  # 3 attempts in total (D-021)

    # LangSmith (declared before the key: the key's validator reads the tracing flag)
    LANGSMITH_TRACING: bool = True
    LANGSMITH_API_KEY: SecretStr | None = Field(default=None, validate_default=True)
    LANGSMITH_PROJECT: str = "octi"
    LANGSMITH_ENDPOINT: str = "https://api.smith.langchain.com"
    LANGSMITH_WORKSPACE_ID: str = ""

    # Pinecone
    PINECONE_API_KEY: SecretStr
    PINECONE_INDEX_NAME: str = Field(default="octi-tables", pattern=r"^[a-z0-9-]{1,45}$")
    PINECONE_NAMESPACE: str = Field(default="octi", min_length=1)

    # Ingestion agent: extra `enrich` attempts per Table after a failed validation, so 3 attempts by
    # default. Capped at 5 so a typo cannot burn the proxy budget (D-054).
    INGESTION_MAX_RETRIES: int = Field(default=2, ge=0, le=5)

    # Analyst agent: extra code attempts after a failed one, so 3 attempts by default (D-092).
    ANALYST_MAX_RETRIES: int = Field(default=2, ge=0, le=5)
    # Wall-clock limit of one sandbox container run; the container is killed after it (D-086).
    SANDBOX_TIMEOUT_SECONDS: int = Field(default=30, ge=5, le=120)

    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @field_validator("LITELLM_BASE_URL")
    @classmethod
    def _normalise_base_url(cls, value: str) -> str:
        """End in exactly one `/v1`, however the user wrote it (FR-003)."""
        base = _check_http_url(value).rstrip("/")
        return base if base.endswith("/v1") else f"{base}/v1"

    @field_validator("LANGSMITH_ENDPOINT")
    @classmethod
    def _check_endpoint(cls, value: str) -> str:
        return _check_http_url(value)

    @field_validator("LITELLM_API_KEY", "PINECONE_API_KEY")
    @classmethod
    def _check_required_secret(cls, value: SecretStr) -> SecretStr:
        _check_secret_length(value)
        return value

    @field_validator("LANGSMITH_API_KEY")
    @classmethod
    def _check_langsmith_key(cls, value: SecretStr | None, info: ValidationInfo) -> SecretStr | None:
        """Required only while tracing is on (D-024)."""
        if value is None and info.data.get("LANGSMITH_TRACING", True):
            raise ValueError("required when LANGSMITH_TRACING is true")
        return _check_secret_length(value)

    @field_validator("LOG_LEVEL", mode="before")
    @classmethod
    def _upper_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @classmethod
    def from_mapping(cls, environment: Mapping[str, str]) -> "Settings":
        """Parse a mapping (normally `os.environ`) into Settings.

        Empty values count as missing. Pydantic's `ValidationError` becomes `InvalidSettingsError`,
        which keeps variable names and reasons but never the values (FR-002).
        """
        raw = {name: environment[name] for name in cls.model_fields if environment.get(name)}
        try:
            return cls.model_validate(raw)
        except ValidationError as exc:
            problems: dict[str, str] = {}
            for error in exc.errors(include_input=False, include_url=False):
                name = str(error["loc"][0]) if error["loc"] else "configuration"
                reason = "missing" if error["type"] == "missing" else error["msg"].removeprefix("Value error, ")
                problems.setdefault(name, reason)
            raise InvalidSettingsError(problems) from None

    @property
    def chat_model_choices(self) -> list[str]:
        """The chat models the user may pick: `LLM_MODEL` (the default) first, then `LLM_MODEL_CHOICES`,
        without blanks or duplicates. The embedding model is never a choice: it fixes the index dimension."""
        names = [self.LLM_MODEL, *(name.strip() for name in self.LLM_MODEL_CHOICES.split(","))]
        return list(dict.fromkeys(name for name in names if name))

    def secret_values(self) -> list[str]:
        """The raw secret strings, for the log redactor only (BR-003 exception)."""
        secrets = (getattr(self, name) for name in SECRET_FIELDS)
        return [secret.get_secret_value() for secret in secrets if secret is not None]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load `.env` and parse the environment once per process (FR-001)."""
    load_environment()
    return Settings.from_mapping(os.environ)
