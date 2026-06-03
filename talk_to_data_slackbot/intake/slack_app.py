from __future__ import annotations

import time
from typing import Any

from slack_bolt import App

from talk_to_data_slackbot.config import Settings, get_settings
from talk_to_data_slackbot.formatter import FormattedMessage
from talk_to_data_slackbot.intake.dedupe import InMemoryEventDeduper
from talk_to_data_slackbot.intake.envelope import RequestEnvelope
from talk_to_data_slackbot.intake.parser import intake_slack_payload
from talk_to_data_slackbot.router import handle_analytics_request

_FALLBACK_ERROR_MESSAGE = (
    "Something went wrong while running your analytics question. Please try again."
)
_PROCESSING_MESSAGE = "⏳ Analyzing your question..."
_TIMED_RESPONSE_PREFIXES = ("*Answer*", "*Results*", "*Chart*")

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

    processing_ts = _post_processing_message(client, envelope, logger)

    start = time.perf_counter()
    try:
        formatted = handle_analytics_request(envelope)
    except Exception:
        logger.exception("Analytics request failed")
        _deliver_slack_message(
            client,
            envelope,
            say,
            processing_ts,
            FormattedMessage(text=_FALLBACK_ERROR_MESSAGE),
            logger,
        )
        return

    elapsed = time.perf_counter() - start
    if _should_append_timing(formatted):
        formatted = _append_timing_footer(formatted, elapsed)

    _deliver_slack_message(client, envelope, say, processing_ts, formatted, logger)

    if formatted.chart_path:
        try:
            client.files_upload_v2(
                channel=envelope.channel_id,
                file=formatted.chart_path,
                thread_ts=envelope.thread_ts,
            )
        except Exception:
            logger.exception("Chart upload failed")


def _post_processing_message(
    client: Any,
    envelope: RequestEnvelope,
    logger: Any,
) -> str | None:
    """Post an immediate processing indicator; return message ``ts`` for later update."""
    try:
        response = client.chat_postMessage(
            channel=envelope.channel_id,
            text=_PROCESSING_MESSAGE,
            thread_ts=envelope.thread_ts,
        )
        message_ts = response.get("ts")
        if isinstance(message_ts, str) and message_ts.strip():
            return message_ts
    except Exception:
        logger.exception("Failed to post processing message")
    return None


def _deliver_slack_message(
    client: Any,
    envelope: RequestEnvelope,
    say: Any,
    message_ts: str | None,
    formatted: FormattedMessage,
    logger: Any,
) -> None:
    """Update the processing message in place, or fall back to ``say()``."""
    if message_ts and _try_chat_update(client, envelope, message_ts, formatted, logger):
        return

    say(
        text=formatted.text,
        blocks=formatted.blocks,
        thread_ts=envelope.thread_ts,
    )


def _try_chat_update(
    client: Any,
    envelope: RequestEnvelope,
    message_ts: str,
    formatted: FormattedMessage,
    logger: Any,
) -> bool:
    kwargs: dict[str, Any] = {
        "channel": envelope.channel_id,
        "ts": message_ts,
        "text": formatted.text,
    }
    if formatted.blocks is not None:
        kwargs["blocks"] = formatted.blocks

    try:
        client.chat_update(**kwargs)
        return True
    except Exception:
        logger.exception("Failed to update processing message")
        return False


def _should_append_timing(formatted: FormattedMessage) -> bool:
    """Return True for successful text, table, and chart responses from Formatter."""
    if formatted.chart_path:
        return True
    return formatted.text.startswith(_TIMED_RESPONSE_PREFIXES)


def _format_timing_footer(elapsed_seconds: float) -> str:
    return f"\n\n⏱ Completed in {elapsed_seconds:.1f}s"


def _append_timing_footer(
    formatted: FormattedMessage,
    elapsed_seconds: float,
) -> FormattedMessage:
    footer = _format_timing_footer(elapsed_seconds)
    new_text = formatted.text + footer
    new_blocks: list[dict[str, Any]] | None = None

    if formatted.blocks:
        new_blocks = []
        for index, block in enumerate(formatted.blocks):
            if index == 0 and block.get("type") == "section":
                text_obj = block.get("text", {})
                new_blocks.append(
                    {
                        **block,
                        "text": {
                            **text_obj,
                            "text": text_obj.get("text", "") + footer,
                        },
                    }
                )
            else:
                new_blocks.append(block)

    return FormattedMessage(
        text=new_text,
        blocks=new_blocks,
        chart_path=formatted.chart_path,
    )


def _validate_slack_settings(settings: Settings) -> None:
    """Ensure tokens required for Socket Mode startup are present."""
    if not settings.slack_bot_token or not settings.slack_bot_token.strip():
        raise ValueError("SLACK_BOT_TOKEN is required for Slack runtime")

    if not settings.slack_app_token or not settings.slack_app_token.strip():
        raise ValueError("SLACK_APP_TOKEN is required for Socket Mode")
