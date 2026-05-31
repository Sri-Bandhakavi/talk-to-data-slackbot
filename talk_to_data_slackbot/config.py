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


@lru_cache
def get_settings() -> Settings:
    return Settings()
