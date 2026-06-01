from __future__ import annotations

import re
from typing import Any

from talk_to_data_slackbot.intake.dedupe import InMemoryEventDeduper
from talk_to_data_slackbot.intake.envelope import RequestEnvelope

_SUPPORTED_EVENT_TYPE = "app_mention"
_USER_MENTION_PATTERN = re.compile(r"<@[^>]+>")


def parse_slack_event(payload: dict[str, Any]) -> RequestEnvelope | None:
    """Parse a Slack Events API payload into a ``RequestEnvelope``.

    Returns ``None`` when the event should be ignored.
    """
    event, event_id = _unwrap_payload(payload)
    if event_id is None or not event_id.strip():
        return None

    if event.get("type") != _SUPPORTED_EVENT_TYPE:
        return None

    if event.get("bot_id") or event.get("subtype") == "bot_message":
        return None

    channel_id = event.get("channel")
    user_id = event.get("user")
    raw_text = event.get("text")

    if not isinstance(channel_id, str) or not channel_id.strip():
        return None
    if not isinstance(user_id, str) or not user_id.strip():
        return None
    if not isinstance(raw_text, str):
        return None

    text = _clean_question_text(raw_text)
    if not text:
        return None

    thread_ts = event.get("ts")
    if not isinstance(thread_ts, str) or not thread_ts.strip():
        thread_ts = None

    return RequestEnvelope(
        event_id=event_id,
        channel_id=channel_id,
        user_id=user_id,
        text=text,
        thread_ts=thread_ts,
    )


def intake_slack_payload(
    payload: dict[str, Any],
    deduper: InMemoryEventDeduper,
) -> RequestEnvelope | None:
    """Apply deduplication, then parse a Slack payload into a request envelope."""
    _, event_id = _unwrap_payload(payload)
    if event_id is None or not event_id.strip():
        return None

    if deduper.is_duplicate(event_id):
        return None

    envelope = parse_slack_event(payload)
    if envelope is None:
        return None

    deduper.mark(event_id)
    return envelope


def _unwrap_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    event = payload.get("event")
    event_id = payload.get("event_id")

    if isinstance(event, dict):
        if isinstance(event_id, str):
            return event, event_id
        return event, None

    if isinstance(event_id, str):
        return payload, event_id

    return payload, None


def _clean_question_text(raw_text: str) -> str:
    without_mentions = _USER_MENTION_PATTERN.sub("", raw_text)
    return without_mentions.strip()
