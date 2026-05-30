from collections.abc import Generator

import pytest
from pydantic import ValidationError

from talk_to_data_slackbot.config import get_settings


@pytest.fixture
def settings_env(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/testdb")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def database_url() -> str:
    get_settings.cache_clear()
    try:
        return get_settings().database_url
    except ValidationError:
        pytest.skip("DATABASE_URL not configured")
