import pytest

from talk_to_data_slackbot import postgres
from talk_to_data_slackbot.config import get_settings

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_ping(database_url: str) -> None:
    assert postgres.ping() is True


def test_execute_read_select_one(database_url: str) -> None:
    rows = postgres.execute_read("SELECT 1 AS value")
    assert rows == [{"value": 1}]
