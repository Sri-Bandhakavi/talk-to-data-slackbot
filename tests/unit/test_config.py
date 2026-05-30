import pytest
from pydantic import ValidationError

from talk_to_data_slackbot.config import Settings, get_settings


def test_settings_loads_from_env(settings_env: None) -> None:
    settings = Settings()
    assert settings.database_url == "postgresql://user:pass@localhost:5432/testdb"
    assert settings.log_level == "DEBUG"


def test_settings_default_log_level(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    settings = Settings()
    assert settings.log_level == "INFO"


def test_missing_database_url_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert "database_url" in str(exc_info.value).lower()


def test_get_settings_is_cached(settings_env: None) -> None:
    first = get_settings()
    second = get_settings()
    assert first is second
