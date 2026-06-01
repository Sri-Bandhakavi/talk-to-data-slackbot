from __future__ import annotations

from talk_to_data_slackbot.formatter import FormattedMessage, format_response
from talk_to_data_slackbot.intake.envelope import RequestEnvelope
from talk_to_data_slackbot.pandas_ai.analytics import run_query


def handle_analytics_request(envelope: RequestEnvelope) -> FormattedMessage:
    """Run analytics for an Intake request and return a formatted Slack payload."""
    result = run_query(envelope.text)
    return format_response(result)
