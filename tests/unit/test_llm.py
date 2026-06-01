from unittest.mock import MagicMock, patch

import pytest

from talk_to_data_slackbot.config import Settings, get_settings
from talk_to_data_slackbot.pandas_ai.llm import (
    LLMConfigurationError,
    build_llm,
    configure_llm,
)


@pytest.fixture
def llm_settings(settings_env: None, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setenv("PANDASAI_MODEL", "gpt-4o-mini")
    get_settings.cache_clear()
    return Settings()


def test_build_llm_creates_litellm_from_settings(llm_settings: Settings) -> None:
    with patch("talk_to_data_slackbot.pandas_ai.llm.LiteLLM") as mock_litellm:
        mock_instance = MagicMock()
        mock_litellm.return_value = mock_instance

        llm = build_llm(llm_settings)

        mock_litellm.assert_called_once_with(
            model="gpt-4o-mini",
            api_key="sk-test-key",
        )
        assert llm is mock_instance


def test_build_llm_missing_api_key_raises(
    settings_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()

    with pytest.raises(LLMConfigurationError, match="OPENAI_API_KEY"):
        build_llm(Settings(_env_file=None))


def test_build_llm_blank_api_key_raises(
    settings_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "   ")
    get_settings.cache_clear()

    with pytest.raises(LLMConfigurationError, match="OPENAI_API_KEY"):
        build_llm(Settings())


def test_configure_llm_registers_with_pandasai(llm_settings: Settings) -> None:
    with patch("talk_to_data_slackbot.pandas_ai.llm.LiteLLM") as mock_litellm:
        mock_instance = MagicMock()
        mock_litellm.return_value = mock_instance

        with patch("talk_to_data_slackbot.pandas_ai.llm.pai.config.set") as mock_set:
            llm = configure_llm(llm_settings)

    mock_set.assert_called_once_with({"llm": mock_instance})
    assert llm is mock_instance
