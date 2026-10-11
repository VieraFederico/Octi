"""Settings: parse the environment once into typed values (spec FR-001 … FR-004a, BR-005)."""

from pathlib import Path

import pytest

from services import settings as settings_module
from services.errors import InvalidSettingsError
from services.settings import Settings, get_settings, load_environment
from tests.stubs import FAKE_LITELLM_KEY, FAKE_PINECONE_KEY


def test_valid_environment_parses_to_typed_values(make_settings) -> None:
    """VC-001: a complete environment yields typed values and the documented defaults."""
    # Given a complete fake environment / When it is parsed
    settings = make_settings()
    # Then values are typed and defaults apply
    assert settings.LLM_MODEL == "fake-chat-model"
    assert settings.EMBEDDING_DIMENSION == 1536
    assert settings.LLM_TEMPERATURE == 0.0
    assert settings.LLM_TIMEOUT_SECONDS == 60
    assert settings.LLM_MAX_RETRIES == 2
    assert settings.LANGSMITH_TRACING is False
    assert settings.PINECONE_INDEX_NAME == "octi-tables"
    assert settings.LITELLM_API_KEY.get_secret_value() == FAKE_LITELLM_KEY


def test_get_settings_builds_once_per_process(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake_env: dict[str, str]
) -> None:
    """VC-001: two calls to get_settings() return the same object."""
    # Given the env file points to an empty temporary file and the environment is complete
    empty_env_file = tmp_path / ".env"
    empty_env_file.write_text("")
    monkeypatch.setattr(settings_module, "ENV_FILE", empty_env_file)
    for key, value in fake_env.items():
        monkeypatch.setenv(key, value)
    # When get_settings() is called twice
    first, second = get_settings(), get_settings()
    # Then it is the very same object
    assert first is second


def test_shell_variables_win_over_env_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """VC-002: a variable already set in the shell is not overridden by the env file."""
    # Given LLM_MODEL=a in the shell and LLM_MODEL=b in an env file
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_MODEL=b\n")
    monkeypatch.setenv("LLM_MODEL", "a")
    # When the env file is loaded
    load_environment(env_file)
    # Then the shell value survives
    import os

    assert os.environ["LLM_MODEL"] == "a"


def test_missing_variables_are_all_named_without_values(fake_env: dict[str, str]) -> None:
    """VC-003: every missing variable is named; no value leaks into the message."""
    # Given LITELLM_API_KEY and LLM_MODEL are missing
    env = {key: value for key, value in fake_env.items() if key not in ("LITELLM_API_KEY", "LLM_MODEL")}
    # When parsing / Then InvalidSettingsError names both, and shows no value
    with pytest.raises(InvalidSettingsError) as caught:
        Settings.from_mapping(env)
    error = caught.value
    assert {"LITELLM_API_KEY", "LLM_MODEL"} <= set(error.fields)
    assert "LITELLM_API_KEY" in error.user_message and "LLM_MODEL" in error.user_message
    assert FAKE_PINECONE_KEY not in error.user_message


def test_empty_value_counts_as_missing(fake_env: dict[str, str]) -> None:
    """VC-003: an empty value is the same failure as a missing one."""
    with pytest.raises(InvalidSettingsError) as caught:
        Settings.from_mapping({**fake_env, "LLM_MODEL": ""})
    assert caught.value.fields == ("LLM_MODEL",)


def test_invalid_index_name_is_rejected(make_settings) -> None:
    """VC-004: Pinecone index names must be lowercase letters, digits and dashes."""
    with pytest.raises(InvalidSettingsError) as caught:
        make_settings(PINECONE_INDEX_NAME="Octi_Tables")
    assert caught.value.fields == ("PINECONE_INDEX_NAME",)


def test_out_of_range_numbers_are_rejected(make_settings) -> None:
    """VC-005: timeout 0 and temperature 3 are both reported."""
    with pytest.raises(InvalidSettingsError) as caught:
        make_settings(LLM_TIMEOUT_SECONDS="0", LLM_TEMPERATURE="3")
    assert set(caught.value.fields) == {"LLM_TIMEOUT_SECONDS", "LLM_TEMPERATURE"}


@pytest.mark.parametrize(
    "raw_url",
    ["https://p.x", "https://p.x/", "https://p.x/v1", "https://p.x/v1/"],
)
def test_base_url_ends_in_exactly_one_v1(make_settings, raw_url: str) -> None:
    """VC-006: the proxy URL is normalised to end in exactly one /v1."""
    assert make_settings(LITELLM_BASE_URL=raw_url).LITELLM_BASE_URL == "https://p.x/v1"


def test_non_http_base_url_is_rejected(make_settings) -> None:
    """VC-006 (failure path): a URL without http(s) scheme is invalid."""
    with pytest.raises(InvalidSettingsError) as caught:
        make_settings(LITELLM_BASE_URL="proxy.example.test")
    assert caught.value.fields == ("LITELLM_BASE_URL",)


def test_secrets_are_masked_everywhere(make_settings) -> None:
    """VC-007: str(), repr() and an exception carrying Settings never show a secret."""
    settings = make_settings()
    rendered = [str(settings), repr(settings), str(RuntimeError(settings))]
    for text in rendered:
        assert FAKE_LITELLM_KEY not in text
        assert FAKE_PINECONE_KEY not in text


def test_short_secret_is_a_configuration_error(make_settings) -> None:
    """VC-007a: a secret shorter than 8 characters cannot be redacted safely."""
    with pytest.raises(InvalidSettingsError) as caught:
        make_settings(PINECONE_API_KEY="abc")
    assert caught.value.fields == ("PINECONE_API_KEY",)
    assert "abc" not in caught.value.user_message


def test_langsmith_key_optional_only_when_tracing_off(make_settings) -> None:
    """VC-007b: tracing off → no key needed; tracing on → key required."""
    # Given tracing off and no key / Then Settings builds
    assert make_settings(LANGSMITH_TRACING="false", LANGSMITH_API_KEY=None).LANGSMITH_API_KEY is None
    # Given tracing on and no key / Then the key is named as missing
    with pytest.raises(InvalidSettingsError) as caught:
        make_settings(LANGSMITH_TRACING="true", LANGSMITH_API_KEY=None)
    assert caught.value.fields == ("LANGSMITH_API_KEY",)


def test_namespace_defaults_to_octi_and_can_be_overridden(make_settings) -> None:
    """VC-007d: PINECONE_NAMESPACE defaults to "octi"."""
    assert make_settings().PINECONE_NAMESPACE == "octi"
    assert make_settings(PINECONE_NAMESPACE="x").PINECONE_NAMESPACE == "x"


def test_chat_model_choices_put_the_default_first_without_duplicates(make_settings) -> None:
    """D-037: LLM_MODEL first, then LLM_MODEL_CHOICES in order; blanks and repeats dropped."""
    settings = make_settings(LLM_MODEL_CHOICES=" model-b ,, fake-chat-model, model-b,model-c ")
    assert settings.chat_model_choices == ["fake-chat-model", "model-b", "model-c"]


def test_chat_model_choices_default_to_llm_model_alone(make_settings) -> None:
    """D-037: no LLM_MODEL_CHOICES → only LLM_MODEL is offered."""
    assert make_settings().chat_model_choices == ["fake-chat-model"]


def test_ingestion_max_retries_defaults_to_2_and_accepts_up_to_5(make_settings) -> None:
    """VC-158 (spec 01 FR-155): unset → 2; "5" → 5."""
    assert make_settings().INGESTION_MAX_RETRIES == 2
    assert make_settings(INGESTION_MAX_RETRIES="5").INGESTION_MAX_RETRIES == 5


@pytest.mark.parametrize("raw_value", ["6", "-1", "two"])
def test_ingestion_max_retries_outside_0_to_5_is_rejected(make_settings, raw_value: str) -> None:
    """VC-158 (spec 01 FR-155): 6, -1 and "two" → InvalidSettingsError naming INGESTION_MAX_RETRIES."""
    with pytest.raises(InvalidSettingsError) as caught:
        make_settings(INGESTION_MAX_RETRIES=raw_value)
    assert caught.value.fields == ("INGESTION_MAX_RETRIES",)
    assert "INGESTION_MAX_RETRIES" in caught.value.user_message


def test_env_example_documents_ingestion_max_retries() -> None:
    """VC-158 (spec 01 FR-155): the versioned example environment file lists the variable."""
    example = (settings_module.REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    assert "INGESTION_MAX_RETRIES" in example
