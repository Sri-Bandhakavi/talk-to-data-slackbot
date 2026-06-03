from unittest.mock import MagicMock, patch

import pytest

from talk_to_data_slackbot.formatter import (
    FormattedMessage,
    format_guardrail_rejection,
    format_response,
)
from talk_to_data_slackbot.intake import RequestEnvelope
from talk_to_data_slackbot.pandas_ai.analytics import AgentResult
from talk_to_data_slackbot.pandas_ai.answerability import (
    AnswerabilityAssessment,
    RejectionKind,
    assess_answerability,
)
from talk_to_data_slackbot.router import handle_analytics_request

TEST_ENVELOPE = RequestEnvelope(
    event_id="Ev0123456789012345678901",
    channel_id="C0123456789",
    user_id="U0123456789",
    text="How many users signed up last month?",
    thread_ts="1710000000.000100",
)

_ANSWERABLE_ASSESSMENT = AnswerabilityAssessment(
    answerable=True,
    kind=RejectionKind.ANSWERABLE,
    question=TEST_ENVELOPE.text,
)


@patch("talk_to_data_slackbot.router.handler.assess_answerability")
@patch("talk_to_data_slackbot.router.handler.run_query")
def test_handle_analytics_request_success_path(
    mock_run_query: MagicMock,
    mock_assess: MagicMock,
) -> None:
    mock_assess.return_value = _ANSWERABLE_ASSESSMENT
    agent_result = AgentResult(
        success=True,
        result_type="text",
        value="There are 42 users signed up last month.",
        question=TEST_ENVELOPE.text,
    )
    mock_run_query.return_value = agent_result

    formatted = handle_analytics_request(TEST_ENVELOPE)

    mock_assess.assert_called_once_with(TEST_ENVELOPE.text)
    mock_run_query.assert_called_once_with(TEST_ENVELOPE.text)
    assert formatted == format_response(agent_result)


@patch("talk_to_data_slackbot.router.handler.assess_answerability")
@patch("talk_to_data_slackbot.router.handler.run_query")
def test_handle_analytics_request_error_path(
    mock_run_query: MagicMock,
    mock_assess: MagicMock,
) -> None:
    mock_assess.return_value = _ANSWERABLE_ASSESSMENT
    agent_result = AgentResult(
        success=False,
        result_type="error",
        value="Something went wrong while running your analytics question. Please try again.",
        question=TEST_ENVELOPE.text,
        error_detail="RuntimeError: agent execution failed",
    )
    mock_run_query.return_value = agent_result

    formatted = handle_analytics_request(TEST_ENVELOPE)

    mock_assess.assert_called_once_with(TEST_ENVELOPE.text)
    mock_run_query.assert_called_once_with(TEST_ENVELOPE.text)
    assert formatted == format_response(agent_result)
    assert formatted.text == (
        "Something went wrong while running your analytics question. Please try again."
    )
    assert "RuntimeError" not in formatted.text


@patch("talk_to_data_slackbot.router.handler.assess_answerability")
@patch("talk_to_data_slackbot.router.handler.run_query")
def test_handle_analytics_request_calls_run_query_with_envelope_text(
    mock_run_query: MagicMock,
    mock_assess: MagicMock,
) -> None:
    mock_assess.return_value = _ANSWERABLE_ASSESSMENT
    mock_run_query.return_value = AgentResult(
        success=True,
        result_type="text",
        value="ok",
        question=TEST_ENVELOPE.text,
    )

    handle_analytics_request(TEST_ENVELOPE)

    mock_assess.assert_called_once_with(TEST_ENVELOPE.text)
    mock_run_query.assert_called_once_with("How many users signed up last month?")


@patch("talk_to_data_slackbot.router.handler.run_query")
def test_handle_analytics_request_reject_does_not_call_run_query(
    mock_run_query: MagicMock,
) -> None:
    envelope = RequestEnvelope(
        event_id=TEST_ENVELOPE.event_id,
        channel_id=TEST_ENVELOPE.channel_id,
        user_id=TEST_ENVELOPE.user_id,
        text="calculate the square root of banana",
        thread_ts=TEST_ENVELOPE.thread_ts,
    )

    formatted = handle_analytics_request(envelope)

    mock_run_query.assert_not_called()
    assessment = assess_answerability(envelope.text)
    assert formatted == format_guardrail_rejection(assessment)


@patch("talk_to_data_slackbot.router.handler.run_query")
@pytest.mark.parametrize(
    "question",
    [
        "Show average customer satisfaction score by product category",
        "Show paying customers by region",
    ],
)
def test_handle_analytics_request_rejects_unsupported_questions(
    mock_run_query: MagicMock,
    question: str,
) -> None:
    envelope = RequestEnvelope(
        event_id=TEST_ENVELOPE.event_id,
        channel_id=TEST_ENVELOPE.channel_id,
        user_id=TEST_ENVELOPE.user_id,
        text=question,
        thread_ts=TEST_ENVELOPE.thread_ts,
    )

    formatted = handle_analytics_request(envelope)

    mock_run_query.assert_not_called()
    assessment = assess_answerability(question)
    assert formatted == format_guardrail_rejection(assessment)


@patch("talk_to_data_slackbot.router.handler.run_query")
def test_handle_analytics_request_accepts_revenue_by_geography(
    mock_run_query: MagicMock,
) -> None:
    question = "Show revenue by geography"
    envelope = RequestEnvelope(
        event_id=TEST_ENVELOPE.event_id,
        channel_id=TEST_ENVELOPE.channel_id,
        user_id=TEST_ENVELOPE.user_id,
        text=question,
        thread_ts=TEST_ENVELOPE.thread_ts,
    )
    agent_result = AgentResult(
        success=True,
        result_type="text",
        value="100",
        question=question,
    )
    mock_run_query.return_value = agent_result

    formatted = handle_analytics_request(envelope)

    mock_run_query.assert_called_once_with(question)
    assert formatted == format_response(agent_result)
