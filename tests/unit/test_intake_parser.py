import json
from pathlib import Path
from typing import Any

from talk_to_data_slackbot.intake import (
    InMemoryEventDeduper,
    RequestEnvelope,
    intake_slack_payload,
    parse_slack_event,
)

SLACK_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "slack"


def _load_slack_fixture(name: str) -> dict[str, Any]:
    fixture_path = SLACK_FIXTURES_DIR / name
    with fixture_path.open(encoding="utf-8") as handle:
        return json.load(handle)


def test_parse_valid_app_mention_returns_request_envelope() -> None:
    payload = _load_slack_fixture("app_mention_valid.json")

    envelope = parse_slack_event(payload)

    assert envelope == RequestEnvelope(
        event_id="Ev0123456789012345678901",
        channel_id="C0123456789",
        user_id="U0123456789",
        text="How many users signed up last month?",
        thread_ts="1710000000.000100",
    )


def test_parse_valid_app_mention_strips_user_mentions() -> None:
    payload = _load_slack_fixture("app_mention_valid.json")

    envelope = parse_slack_event(payload)

    assert envelope is not None
    assert "<@" not in envelope.text
    assert envelope.text == "How many users signed up last month?"


def test_parse_bot_message_returns_none() -> None:
    payload = _load_slack_fixture("app_mention_bot_message.json")

    assert parse_slack_event(payload) is None


def test_parse_empty_text_returns_none() -> None:
    payload = _load_slack_fixture("app_mention_empty_text.json")

    assert parse_slack_event(payload) is None


def test_parse_unsupported_event_type_returns_none() -> None:
    payload = _load_slack_fixture("app_mention_valid.json")
    payload["event"]["type"] = "message"

    assert parse_slack_event(payload) is None


def test_parse_missing_event_id_returns_none() -> None:
    payload = _load_slack_fixture("app_mention_valid.json")
    del payload["event_id"]

    assert parse_slack_event(payload) is None


def test_intake_slack_payload_duplicate_event_id_returns_none_on_second_call() -> None:
    payload = _load_slack_fixture("app_mention_valid.json")
    deduper = InMemoryEventDeduper()

    first = intake_slack_payload(payload, deduper)
    second = intake_slack_payload(payload, deduper)

    assert first == RequestEnvelope(
        event_id="Ev0123456789012345678901",
        channel_id="C0123456789",
        user_id="U0123456789",
        text="How many users signed up last month?",
        thread_ts="1710000000.000100",
    )
    assert second is None


def test_intake_slack_payload_missing_event_id_returns_none() -> None:
    payload = _load_slack_fixture("app_mention_valid.json")
    del payload["event_id"]
    deduper = InMemoryEventDeduper()

    assert intake_slack_payload(payload, deduper) is None
