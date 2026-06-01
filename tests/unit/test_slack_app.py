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


@patch("talk_to_data_slackbot.intake.slack_app.handle_analytics_request")
@patch("talk_to_data_slackbot.intake.slack_app.intake_slack_payload")
def test_on_app_mention_calls_router_and_say_on_success(
    mock_intake: MagicMock,
    mock_router: MagicMock,
) -> None:
    mock_intake.return_value = TEST_ENVELOPE
    mock_router.return_value = FormattedMessage(
        text="There are 42 users signed up last month.",
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "There are 42 users signed up last month.",
                },
            }
        ],
    )
    mock_say = MagicMock()

    _on_app_mention(
        body=_load_slack_fixture("app_mention_valid.json"),
        say=mock_say,
        client=MagicMock(),
        logger=MagicMock(),
    )

    mock_router.assert_called_once_with(TEST_ENVELOPE)
    mock_say.assert_called_once_with(
        text="There are 42 users signed up last month.",
        blocks=mock_router.return_value.blocks,
        thread_ts=TEST_ENVELOPE.thread_ts,
    )


@patch("talk_to_data_slackbot.intake.slack_app.handle_analytics_request")
@patch("talk_to_data_slackbot.intake.slack_app.intake_slack_payload")
def test_on_app_mention_passes_body_to_intake(
    mock_intake: MagicMock,
    mock_router: MagicMock,
) -> None:
    body = _load_slack_fixture("app_mention_valid.json")
    mock_intake.return_value = TEST_ENVELOPE
    mock_router.return_value = FormattedMessage(text="ok")

    _on_app_mention(
        body=body,
        say=MagicMock(),
        client=MagicMock(),
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

    _on_app_mention(
        body=_load_slack_fixture("app_mention_valid.json"),
        say=mock_say,
        client=MagicMock(),
        logger=MagicMock(),
    )

    mock_say.assert_called_once_with(
        text=(
            "Something went wrong while running your analytics question. "
            "Please try again."
        ),
        blocks=mock_router.return_value.blocks,
        thread_ts=TEST_ENVELOPE.thread_ts,
    )
    assert "RuntimeError" not in mock_say.call_args.kwargs["text"]


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

    _on_app_mention(
        body=_load_slack_fixture("app_mention_valid.json"),
        say=mock_say,
        client=MagicMock(),
        logger=mock_logger,
    )

    mock_logger.exception.assert_called_once()
    mock_say.assert_called_once_with(
        text=_FALLBACK_ERROR_MESSAGE,
        thread_ts=TEST_ENVELOPE.thread_ts,
    )
    assert "RuntimeError" not in mock_say.call_args.kwargs["text"]


@patch("talk_to_data_slackbot.intake.slack_app.handle_analytics_request")
@patch("talk_to_data_slackbot.intake.slack_app.intake_slack_payload")
def test_on_app_mention_uploads_chart_when_chart_path_set(
    mock_intake: MagicMock,
    mock_router: MagicMock,
) -> None:
    mock_intake.return_value = TEST_ENVELOPE
    mock_router.return_value = FormattedMessage(
        text="I've generated a chart for your question.",
        chart_path="/tmp/test_chart.png",
    )
    mock_client = MagicMock()

    _on_app_mention(
        body=_load_slack_fixture("app_mention_valid.json"),
        say=MagicMock(),
        client=mock_client,
        logger=MagicMock(),
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
    mock_client = MagicMock()

    _on_app_mention(
        body=_load_slack_fixture("app_mention_valid.json"),
        say=MagicMock(),
        client=mock_client,
        logger=MagicMock(),
    )

    mock_client.files_upload_v2.assert_not_called()
