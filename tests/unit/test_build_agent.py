from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from talk_to_data_slackbot.config import Settings
from talk_to_data_slackbot.pandas_ai.analytics import (
    DatasetRegistrationError,
    build_agent,
)
from talk_to_data_slackbot.pandas_ai.llm import LLMConfigurationError

TEST_DATABASE_URL = "postgresql://runtime_user:runtime_pass@db.example.com:5433/runtime_db"


@pytest.fixture
def agent_settings(settings_env: None, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setenv("PANDASAI_MODEL", "gpt-4o-mini")
    return Settings()


@patch("talk_to_data_slackbot.pandas_ai.analytics.Agent")
@patch("talk_to_data_slackbot.pandas_ai.analytics.build_datasets")
@patch("talk_to_data_slackbot.pandas_ai.analytics.configure_llm")
def test_build_agent_integrates_llm_datasets_and_agent(
    mock_configure_llm: MagicMock,
    mock_build_datasets: MagicMock,
    mock_agent: MagicMock,
    agent_settings: Settings,
    tmp_path: Path,
) -> None:
    dataset_handles = [MagicMock(name=name) for name in ("payments", "sessions", "subscriptions", "users")]
    mock_build_datasets.return_value = dataset_handles
    mock_agent_instance = MagicMock(name="agent")
    mock_agent.return_value = mock_agent_instance

    agent = build_agent(
        settings=agent_settings,
        database_url=TEST_DATABASE_URL,
        datasets_root=tmp_path,
    )

    mock_configure_llm.assert_called_once_with(agent_settings)
    mock_build_datasets.assert_called_once_with(
        database_url=TEST_DATABASE_URL,
        models_dir=None,
        datasets_root=tmp_path,
        expected_models=frozenset({"users", "subscriptions", "sessions", "payments"}),
    )
    mock_agent.assert_called_once_with(dataset_handles)
    assert agent is mock_agent_instance


@patch("talk_to_data_slackbot.pandas_ai.analytics.Agent")
@patch("talk_to_data_slackbot.pandas_ai.analytics.build_datasets")
@patch("talk_to_data_slackbot.pandas_ai.analytics.configure_llm")
def test_build_agent_propagates_llm_configuration_error(
    mock_configure_llm: MagicMock,
    mock_build_datasets: MagicMock,
    mock_agent: MagicMock,
    agent_settings: Settings,
) -> None:
    mock_configure_llm.side_effect = LLMConfigurationError("OPENAI_API_KEY is required")

    with pytest.raises(LLMConfigurationError, match="OPENAI_API_KEY"):
        build_agent(settings=agent_settings, database_url=TEST_DATABASE_URL)

    mock_build_datasets.assert_not_called()
    mock_agent.assert_not_called()


@patch("talk_to_data_slackbot.pandas_ai.analytics.Agent")
@patch("talk_to_data_slackbot.pandas_ai.analytics.build_datasets")
@patch("talk_to_data_slackbot.pandas_ai.analytics.configure_llm")
def test_build_agent_propagates_dataset_registration_error(
    mock_configure_llm: MagicMock,
    mock_build_datasets: MagicMock,
    mock_agent: MagicMock,
    agent_settings: Settings,
) -> None:
    mock_build_datasets.side_effect = DatasetRegistrationError("missing: users")

    with pytest.raises(DatasetRegistrationError, match="missing: users"):
        build_agent(settings=agent_settings, database_url=TEST_DATABASE_URL)

    mock_configure_llm.assert_called_once_with(agent_settings)
    mock_agent.assert_not_called()


@patch("talk_to_data_slackbot.pandas_ai.analytics.Agent")
@patch("talk_to_data_slackbot.pandas_ai.analytics.build_datasets")
@patch("talk_to_data_slackbot.pandas_ai.analytics.configure_llm")
def test_build_agent_raises_when_no_datasets_registered(
    mock_configure_llm: MagicMock,
    mock_build_datasets: MagicMock,
    mock_agent: MagicMock,
    agent_settings: Settings,
) -> None:
    mock_build_datasets.return_value = []

    with pytest.raises(DatasetRegistrationError, match="No datasets registered"):
        build_agent(
            settings=agent_settings,
            database_url=TEST_DATABASE_URL,
            expected_models=frozenset(),
        )

    mock_agent.assert_not_called()
