from __future__ import annotations

from typing import Any

from slack_bolt import App

from talk_to_data_slackbot.config import Settings, get_settings
from talk_to_data_slackbot.intake.dedupe import InMemoryEventDeduper
from talk_to_data_slackbot.intake.parser import intake_slack_payload
from talk_to_data_slackbot.router import handle_analytics_request

_FALLBACK_ERROR_MESSAGE = (
    "Something went wrong while running your analytics question. Please try again."
)

_deduper = InMemoryEventDeduper()


def create_app(settings: Settings | None = None) -> App:
    """Create a Slack Bolt app with the ``app_mention`` analytics handler registered."""
    resolved = settings or get_settings()
    _validate_slack_settings(resolved)

    app = App(token=resolved.slack_bot_token.strip())
    app.event("app_mention")(_on_app_mention)
    return app


def _on_app_mention(
    body: dict[str, Any],
    say: Any,
    client: Any,
    logger: Any,
    event: dict[str, Any] | None = None,
) -> None:
    """Handle ``app_mention`` events: Intake → Router → Slack reply."""
    envelope = intake_slack_payload(body, _deduper)
    if envelope is None:
        return

    try:
        formatted = handle_analytics_request(envelope)
    except Exception:
        logger.exception("Analytics request failed")
        say(text=_FALLBACK_ERROR_MESSAGE, thread_ts=envelope.thread_ts)
        return

    say(
        text=formatted.text,
        blocks=formatted.blocks,
        thread_ts=envelope.thread_ts,
    )

    if formatted.chart_path:
        try:
            client.files_upload_v2(
                channel=envelope.channel_id,
                file=formatted.chart_path,
                thread_ts=envelope.thread_ts,
            )
        except Exception:
            logger.exception("Chart upload failed")


def _validate_slack_settings(settings: Settings) -> None:
    """Ensure tokens required for Socket Mode startup are present."""
    if not settings.slack_bot_token or not settings.slack_bot_token.strip():
        raise ValueError("SLACK_BOT_TOKEN is required for Slack runtime")

    if not settings.slack_app_token or not settings.slack_app_token.strip():
        raise ValueError("SLACK_APP_TOKEN is required for Socket Mode")
