from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(..., validation_alias="DATABASE_URL")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    openai_api_key: str | None = Field(
        default=None, validation_alias="OPENAI_API_KEY"
    )
    pandasai_model: str = Field(
        default="gpt-4o-mini", validation_alias="PANDASAI_MODEL"
    )
    use_llm_answerability: bool = Field(
        default=False, validation_alias="USE_LLM_ANSWERABILITY"
    )
    answerability_model: str | None = Field(
        default=None, validation_alias="ANSWERABILITY_MODEL"
    )
    answerability_timeout_seconds: float = Field(
        default=10.0, validation_alias="ANSWERABILITY_TIMEOUT_SECONDS"
    )
    answerability_fallback_on_error: bool = Field(
        default=True, validation_alias="ANSWERABILITY_FALLBACK_ON_ERROR"
    )
    slack_bot_token: str | None = Field(
        default=None, validation_alias="SLACK_BOT_TOKEN"
    )
    slack_app_token: str | None = Field(
        default=None, validation_alias="SLACK_APP_TOKEN"
    )
    slack_signing_secret: str | None = Field(
        default=None, validation_alias="SLACK_SIGNING_SECRET"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
