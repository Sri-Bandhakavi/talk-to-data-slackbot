from __future__ import annotations

import pandasai as pai
from pandasai_litellm import LiteLLM

from talk_to_data_slackbot.config import Settings, get_settings


class LLMConfigurationError(Exception):
    """Raised when PandasAI LLM settings are missing or invalid."""


def build_llm(settings: Settings | None = None) -> LiteLLM:
    """Construct a LiteLLM instance from application settings."""
    resolved = settings or get_settings()
    api_key = resolved.openai_api_key

    if api_key is None or not api_key.strip():
        raise LLMConfigurationError(
            "OPENAI_API_KEY is required for PandasAI LLM setup"
        )

    return LiteLLM(model=resolved.pandasai_model, api_key=api_key.strip())


def build_answerability_llm(settings: Settings | None = None) -> LiteLLM:
    """Construct a LiteLLM instance for the answerability classifier."""
    resolved = settings or get_settings()
    api_key = resolved.openai_api_key

    if api_key is None or not api_key.strip():
        raise LLMConfigurationError(
            "OPENAI_API_KEY is required for answerability LLM setup"
        )

    model = resolved.answerability_model or resolved.pandasai_model
    return LiteLLM(
        model=model,
        api_key=api_key.strip(),
        timeout=resolved.answerability_timeout_seconds,
        response_format={"type": "json_object"},
    )


def configure_llm(settings: Settings | None = None) -> LiteLLM:
    """Register the application LiteLLM instance with PandasAI global config."""
    llm = build_llm(settings)
    pai.config.set({"llm": llm})
    return llm
