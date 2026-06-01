from __future__ import annotations

from slack_bolt.adapter.socket_mode import SocketModeHandler

from talk_to_data_slackbot.config import get_settings
from talk_to_data_slackbot.intake.slack_app import create_app


def main() -> None:
    settings = get_settings()
    app = create_app(settings)
    handler = SocketModeHandler(app, settings.slack_app_token.strip())
    handler.start()


if __name__ == "__main__":
    main()
