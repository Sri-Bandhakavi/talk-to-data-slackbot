from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from talk_to_data_slackbot.config import Settings
from talk_to_data_slackbot.pandas_ai.analytics import (
    AgentResult,
    DatasetRegistrationError,
    DatabaseUrlError,
    normalize_agent_response,
    run_query,
)
from talk_to_data_slackbot.pandas_ai.llm import LLMConfigurationError

TEST_DATABASE_URL = "postgresql://runtime_user:runtime_pass@db.example.com:5433/runtime_db"


class _MockAgentResponse:
    def __init__(
        self,
        *,
        type: str,
        value: object,
        error: str | None = None,
    ) -> None:
        self.type = type
        self.value = value
        self.error = error


def test_normalize_string_response() -> None:
    result = normalize_agent_response(
        "How many users?",
        _MockAgentResponse(type="string", value="There are 42 users."),
    )

    assert result == AgentResult(
        success=True,
        result_type="text",
        value="There are 42 users.",
        question="How many users?",
    )


def test_normalize_number_response_as_text() -> None:
    result = normalize_agent_response(
        "Total revenue?",
        _MockAgentResponse(type="number", value=1234.5),
    )

    assert result.success is True
    assert result.result_type == "text"
    assert result.value == "1234.5"


def test_normalize_dataframe_response() -> None:
    frame = pd.DataFrame({"country": ["US", "CA"], "users": [10, 5]})

    result = normalize_agent_response(
        "Users by country",
        _MockAgentResponse(type="dataframe", value=frame),
    )

    assert result.success is True
    assert result.result_type == "dataframe"
    assert "US" in result.value
    assert "users" in result.value


def test_normalize_chart_response() -> None:
    result = normalize_agent_response(
        "Plot signups",
        _MockAgentResponse(type="chart", value="/tmp/chart.png"),
    )

    assert result == AgentResult(
        success=True,
        result_type="chart",
        value="/tmp/chart.png",
        question="Plot signups",
    )


def test_normalize_error_response() -> None:
    result = normalize_agent_response(
        "Bad question",
        _MockAgentResponse(
            type="error",
            value="Unable to answer.",
            error="CodeExecutionError: division by zero",
        ),
    )

    assert result.success is False
    assert result.result_type == "error"
    assert result.value == "Unable to answer."
    assert result.error_detail == "CodeExecutionError: division by zero"


@patch("talk_to_data_slackbot.pandas_ai.analytics.build_agent")
def test_run_query_returns_normalized_success_result(
    mock_build_agent: MagicMock,
) -> None:
    mock_agent = MagicMock()
    mock_agent.chat.return_value = _MockAgentResponse(
        type="string",
        value="42 users signed up.",
    )
    mock_build_agent.return_value = mock_agent

    result = run_query(
        "How many users signed up?",
        database_url=TEST_DATABASE_URL,
    )

    mock_build_agent.assert_called_once()
    mock_agent.chat.assert_called_once_with("How many users signed up?")
    assert result.success is True
    assert result.result_type == "text"
    assert result.value == "42 users signed up."
    assert result.question == "How many users signed up?"


@patch("talk_to_data_slackbot.pandas_ai.analytics.build_agent")
def test_run_query_maps_llm_configuration_error(
    mock_build_agent: MagicMock,
) -> None:
    mock_build_agent.side_effect = LLMConfigurationError("OPENAI_API_KEY is required")

    result = run_query("How many users?", database_url=TEST_DATABASE_URL)

    assert result.success is False
    assert result.result_type == "error"
    assert "OPENAI_API_KEY" in result.value
    assert result.error_detail == "OPENAI_API_KEY is required"


@patch("talk_to_data_slackbot.pandas_ai.analytics.build_agent")
def test_run_query_maps_dataset_registration_error(
    mock_build_agent: MagicMock,
) -> None:
    mock_build_agent.side_effect = DatasetRegistrationError("missing: users")

    result = run_query("How many users?", database_url=TEST_DATABASE_URL)

    assert result.success is False
    assert result.result_type == "error"
    assert "datasets" in result.value.lower()
    assert result.error_detail == "missing: users"


@patch("talk_to_data_slackbot.pandas_ai.analytics.build_agent")
def test_run_query_maps_database_url_error(
    mock_build_agent: MagicMock,
) -> None:
    mock_build_agent.side_effect = DatabaseUrlError("DATABASE_URL must include a username")

    result = run_query("How many users?", database_url=TEST_DATABASE_URL)

    assert result.success is False
    assert result.result_type == "error"
    assert "DATABASE_URL" in result.value
    assert "username" in result.error_detail


@patch("talk_to_data_slackbot.pandas_ai.analytics.build_agent")
def test_run_query_maps_unexpected_agent_failure(
    mock_build_agent: MagicMock,
) -> None:
    mock_agent = MagicMock()
    mock_agent.chat.side_effect = RuntimeError("agent execution failed")
    mock_build_agent.return_value = mock_agent

    result = run_query("How many users?", database_url=TEST_DATABASE_URL)

    assert result.success is False
    assert result.result_type == "error"
    assert "Something went wrong" in result.value
    assert "RuntimeError: agent execution failed" in result.error_detail


@patch("talk_to_data_slackbot.pandas_ai.analytics.build_agent")
def test_run_query_passes_settings_to_build_agent(
    mock_build_agent: MagicMock,
    settings_env: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    settings = Settings()

    mock_agent = MagicMock()
    mock_agent.chat.return_value = _MockAgentResponse(type="string", value="ok")
    mock_build_agent.return_value = mock_agent

    run_query(
        "Question?",
        settings=settings,
        database_url=TEST_DATABASE_URL,
        datasets_root=tmp_path,
    )

    mock_build_agent.assert_called_once_with(
        settings=settings,
        database_url=TEST_DATABASE_URL,
        models_dir=None,
        datasets_root=tmp_path,
        expected_models=frozenset({"users", "subscriptions", "sessions", "payments"}),
    )
