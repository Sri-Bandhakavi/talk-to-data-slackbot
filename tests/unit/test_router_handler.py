from unittest.mock import MagicMock, patch

from talk_to_data_slackbot.formatter import FormattedMessage, format_response
from talk_to_data_slackbot.intake import RequestEnvelope
from talk_to_data_slackbot.pandas_ai.analytics import AgentResult
from talk_to_data_slackbot.router import handle_analytics_request

TEST_ENVELOPE = RequestEnvelope(
    event_id="Ev0123456789012345678901",
    channel_id="C0123456789",
    user_id="U0123456789",
    text="How many users signed up last month?",
    thread_ts="1710000000.000100",
)


@patch("talk_to_data_slackbot.router.handler.run_query")
def test_handle_analytics_request_success_path(mock_run_query: MagicMock) -> None:
    agent_result = AgentResult(
        success=True,
        result_type="text",
        value="There are 42 users signed up last month.",
        question=TEST_ENVELOPE.text,
    )
    mock_run_query.return_value = agent_result

    formatted = handle_analytics_request(TEST_ENVELOPE)

    mock_run_query.assert_called_once_with(TEST_ENVELOPE.text)
    assert formatted == format_response(agent_result)


@patch("talk_to_data_slackbot.router.handler.run_query")
def test_handle_analytics_request_error_path(mock_run_query: MagicMock) -> None:
    agent_result = AgentResult(
        success=False,
        result_type="error",
        value="Something went wrong while running your analytics question. Please try again.",
        question=TEST_ENVELOPE.text,
        error_detail="RuntimeError: agent execution failed",
    )
    mock_run_query.return_value = agent_result

    formatted = handle_analytics_request(TEST_ENVELOPE)

    mock_run_query.assert_called_once_with(TEST_ENVELOPE.text)
    assert formatted == format_response(agent_result)
    assert formatted.text == (
        "Something went wrong while running your analytics question. Please try again."
    )
    assert "RuntimeError" not in formatted.text


@patch("talk_to_data_slackbot.router.handler.run_query")
def test_handle_analytics_request_calls_run_query_with_envelope_text(
    mock_run_query: MagicMock,
) -> None:
    mock_run_query.return_value = AgentResult(
        success=True,
        result_type="text",
        value="ok",
        question=TEST_ENVELOPE.text,
    )

    handle_analytics_request(TEST_ENVELOPE)

    mock_run_query.assert_called_once_with("How many users signed up last month?")
