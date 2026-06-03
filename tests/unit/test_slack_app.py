import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from slack_bolt import App

from talk_to_data_slackbot.config import Settings
from talk_to_data_slackbot.formatter import FormattedMessage
from talk_to_data_slackbot.intake import RequestEnvelope
from talk_to_data_slackbot.intake.slack_app import (
    _FALLBACK_ERROR_MESSAGE,
    _PROCESSING_MESSAGE,
    _append_timing_footer,
    _on_app_mention,
    create_app,
)

SLACK_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "slack"

TEST_ENVELOPE = RequestEnvelope(
    event_id="Ev0123456789012345678901",
    channel_id="C0123456789",
    user_id="U0123456789",
    text="How many users signed up last month?",
    thread_ts="1710000000.000100",
)


def _load_slack_fixture(name: str) -> dict[str, Any]:
    fixture_path = SLACK_FIXTURES_DIR / name
    with fixture_path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _valid_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": "postgresql://user:pass@localhost:5432/testdb",
        "slack_bot_token": "xoxb-test-token",
        "slack_app_token": "xapp-test-token",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _mock_slack_client(message_ts: str = "1234.5678") -> MagicMock:
    mock_client = MagicMock()
    mock_client.chat_postMessage.return_value = {"ts": message_ts, "ok": True}
    return mock_client


def test_create_app_raises_when_slack_bot_token_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    with pytest.raises(ValueError, match="SLACK_BOT_TOKEN"):
        create_app(_valid_settings(slack_bot_token=None))


def test_create_app_raises_when_slack_app_token_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SLACK_APP_TOKEN", raising=False)
    with pytest.raises(ValueError, match="SLACK_APP_TOKEN"):
        create_app(_valid_settings(slack_app_token=None))


def test_create_app_returns_bolt_app_with_valid_settings() -> None:
    app = create_app(_valid_settings())

    assert isinstance(app, App)


@patch("talk_to_data_slackbot.intake.slack_app.handle_analytics_request")
@patch("talk_to_data_slackbot.intake.slack_app.intake_slack_payload")
def test_on_app_mention_ignores_when_intake_returns_none(
    mock_intake: MagicMock,
    mock_router: MagicMock,
) -> None:
    mock_intake.return_value = None
    mock_say = MagicMock()

    _on_app_mention(
        body=_load_slack_fixture("app_mention_valid.json"),
        say=mock_say,
        client=MagicMock(),
        logger=MagicMock(),
    )

    mock_router.assert_not_called()
    mock_say.assert_not_called()


@patch("talk_to_data_slackbot.intake.slack_app.time.perf_counter", side_effect=[0.0, 1.4])
@patch("talk_to_data_slackbot.intake.slack_app.handle_analytics_request")
@patch("talk_to_data_slackbot.intake.slack_app.intake_slack_payload")
def test_on_app_mention_calls_router_and_updates_processing_message(
    mock_intake: MagicMock,
    mock_router: MagicMock,
    mock_perf_counter: MagicMock,
) -> None:
    mock_intake.return_value = TEST_ENVELOPE
    body_text = "*Answer*\n\nThere are 42 users signed up last month."
    mock_router.return_value = FormattedMessage(
        text=body_text,
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": body_text,
                },
            }
        ],
    )
    mock_say = MagicMock()
    mock_client = _mock_slack_client()

    _on_app_mention(
        body=_load_slack_fixture("app_mention_valid.json"),
        say=mock_say,
        client=mock_client,
        logger=MagicMock(),
    )

    mock_router.assert_called_once_with(TEST_ENVELOPE)
    mock_client.chat_postMessage.assert_called_once_with(
        channel=TEST_ENVELOPE.channel_id,
        text=_PROCESSING_MESSAGE,
        thread_ts=TEST_ENVELOPE.thread_ts,
    )
    final_text = body_text + "\n\n⏱ Completed in 1.4s"
    final_formatted = _append_timing_footer(mock_router.return_value, 1.4)
    mock_client.chat_update.assert_called_once_with(
        channel=TEST_ENVELOPE.channel_id,
        ts="1234.5678",
        text=final_text,
        blocks=final_formatted.blocks,
    )
    mock_say.assert_not_called()


@patch("talk_to_data_slackbot.intake.slack_app.handle_analytics_request")
@patch("talk_to_data_slackbot.intake.slack_app.intake_slack_payload")
def test_on_app_mention_passes_body_to_intake(
    mock_intake: MagicMock,
    mock_router: MagicMock,
) -> None:
    body = _load_slack_fixture("app_mention_valid.json")
    mock_intake.return_value = TEST_ENVELOPE
    mock_router.return_value = FormattedMessage(text="ok")
    mock_client = _mock_slack_client()

    _on_app_mention(
        body=body,
        say=MagicMock(),
        client=mock_client,
        logger=MagicMock(),
    )

    mock_intake.assert_called_once()
    assert mock_intake.call_args.args[0] is body


@patch("talk_to_data_slackbot.intake.slack_app.handle_analytics_request")
@patch("talk_to_data_slackbot.intake.slack_app.intake_slack_payload")
def test_on_app_mention_posts_formatted_error_without_router_raise(
    mock_intake: MagicMock,
    mock_router: MagicMock,
) -> None:
    mock_intake.return_value = TEST_ENVELOPE
    mock_router.return_value = FormattedMessage(
        text="Something went wrong while running your analytics question. Please try again.",
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "Something went wrong while running your analytics "
                        "question. Please try again."
                    ),
                },
            }
        ],
    )
    mock_say = MagicMock()
    mock_client = _mock_slack_client()

    _on_app_mention(
        body=_load_slack_fixture("app_mention_valid.json"),
        say=mock_say,
        client=mock_client,
        logger=MagicMock(),
    )

    error_text = (
        "Something went wrong while running your analytics question. "
        "Please try again."
    )
    mock_client.chat_update.assert_called_once_with(
        channel=TEST_ENVELOPE.channel_id,
        ts="1234.5678",
        text=error_text,
        blocks=mock_router.return_value.blocks,
    )
    mock_say.assert_not_called()
    assert "RuntimeError" not in error_text
    assert "⏱ Completed" not in error_text


@patch("talk_to_data_slackbot.intake.slack_app.handle_analytics_request")
@patch("talk_to_data_slackbot.intake.slack_app.intake_slack_payload")
def test_on_app_mention_fallback_say_when_router_raises(
    mock_intake: MagicMock,
    mock_router: MagicMock,
) -> None:
    mock_intake.return_value = TEST_ENVELOPE
    mock_router.side_effect = RuntimeError("unexpected router failure")
    mock_say = MagicMock()
    mock_logger = MagicMock()
    mock_client = _mock_slack_client()

    _on_app_mention(
        body=_load_slack_fixture("app_mention_valid.json"),
        say=mock_say,
        client=mock_client,
        logger=mock_logger,
    )

    mock_logger.exception.assert_called_once()
    mock_client.chat_update.assert_called_once_with(
        channel=TEST_ENVELOPE.channel_id,
        ts="1234.5678",
        text=_FALLBACK_ERROR_MESSAGE,
    )
    mock_say.assert_not_called()
    assert "RuntimeError" not in _FALLBACK_ERROR_MESSAGE
    assert "⏱ Completed" not in _FALLBACK_ERROR_MESSAGE


@patch("talk_to_data_slackbot.intake.slack_app.time.perf_counter", side_effect=[10.0, 12.5])
@patch("talk_to_data_slackbot.intake.slack_app.handle_analytics_request")
@patch("talk_to_data_slackbot.intake.slack_app.intake_slack_payload")
def test_on_app_mention_uploads_chart_when_chart_path_set(
    mock_intake: MagicMock,
    mock_router: MagicMock,
    mock_perf_counter: MagicMock,
) -> None:
    mock_intake.return_value = TEST_ENVELOPE
    body_text = "*Chart*\n\nI've generated a chart for your question."
    mock_router.return_value = FormattedMessage(
        text=body_text,
        chart_path="/tmp/test_chart.png",
    )
    mock_client = _mock_slack_client()
    mock_say = MagicMock()

    _on_app_mention(
        body=_load_slack_fixture("app_mention_valid.json"),
        say=mock_say,
        client=mock_client,
        logger=MagicMock(),
    )

    mock_say.assert_not_called()
    assert mock_client.chat_update.call_args.kwargs["text"].endswith(
        "⏱ Completed in 2.5s"
    )
    mock_client.files_upload_v2.assert_called_once_with(
        channel=TEST_ENVELOPE.channel_id,
        file="/tmp/test_chart.png",
        thread_ts=TEST_ENVELOPE.thread_ts,
    )


@patch("talk_to_data_slackbot.intake.slack_app.handle_analytics_request")
@patch("talk_to_data_slackbot.intake.slack_app.intake_slack_payload")
def test_on_app_mention_skips_upload_when_chart_path_none(
    mock_intake: MagicMock,
    mock_router: MagicMock,
) -> None:
    mock_intake.return_value = TEST_ENVELOPE
    mock_router.return_value = FormattedMessage(text="Answer text only.")
    mock_client = _mock_slack_client()

    _on_app_mention(
        body=_load_slack_fixture("app_mention_valid.json"),
        say=MagicMock(),
        client=mock_client,
        logger=MagicMock(),
    )

    mock_client.files_upload_v2.assert_not_called()


@patch("talk_to_data_slackbot.intake.slack_app.time.perf_counter", side_effect=[0.0, 0.05])
@patch("talk_to_data_slackbot.intake.slack_app.handle_analytics_request")
@patch("talk_to_data_slackbot.intake.slack_app.intake_slack_payload")
def test_on_app_mention_appends_timing_for_table_response(
    mock_intake: MagicMock,
    mock_router: MagicMock,
    mock_perf_counter: MagicMock,
) -> None:
    mock_intake.return_value = TEST_ENVELOPE
    table = "country  users\nUS       10"
    body_text = f"*Results*\n\n```{table}```"
    mock_router.return_value = FormattedMessage(
        text=body_text,
        blocks=[
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": body_text},
            }
        ],
    )
    mock_say = MagicMock()
    mock_client = _mock_slack_client()

    _on_app_mention(
        body=_load_slack_fixture("app_mention_valid.json"),
        say=mock_say,
        client=mock_client,
        logger=MagicMock(),
    )

    final_text = body_text + "\n\n⏱ Completed in 0.1s"
    final_formatted = _append_timing_footer(mock_router.return_value, 0.05)
    mock_client.chat_update.assert_called_once_with(
        channel=TEST_ENVELOPE.channel_id,
        ts="1234.5678",
        text=final_text,
        blocks=final_formatted.blocks,
    )
    mock_say.assert_not_called()


@patch("talk_to_data_slackbot.intake.slack_app.time.perf_counter", side_effect=[0.0, 1.0])
@patch("talk_to_data_slackbot.intake.slack_app.handle_analytics_request")
@patch("talk_to_data_slackbot.intake.slack_app.intake_slack_payload")
def test_on_app_mention_falls_back_to_say_when_chat_update_fails(
    mock_intake: MagicMock,
    mock_router: MagicMock,
    mock_perf_counter: MagicMock,
) -> None:
    mock_intake.return_value = TEST_ENVELOPE
    body_text = "*Answer*\n\n42"
    mock_router.return_value = FormattedMessage(text=body_text)
    mock_client = _mock_slack_client()
    mock_client.chat_update.side_effect = RuntimeError("update failed")
    mock_say = MagicMock()
    mock_logger = MagicMock()

    _on_app_mention(
        body=_load_slack_fixture("app_mention_valid.json"),
        say=mock_say,
        client=mock_client,
        logger=mock_logger,
    )

    mock_logger.exception.assert_called_once()
    expected = _append_timing_footer(mock_router.return_value, 1.0)
    mock_say.assert_called_once_with(
        text=expected.text,
        blocks=expected.blocks,
        thread_ts=TEST_ENVELOPE.thread_ts,
    )
