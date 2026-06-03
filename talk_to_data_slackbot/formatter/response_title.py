from __future__ import annotations

import re

from talk_to_data_slackbot.pandas_ai.answerability import _STOPWORDS
from talk_to_data_slackbot.pandas_ai.answerability_synonyms import apply_synonyms
from talk_to_data_slackbot.pandas_ai.answerability_vocabulary import (
    ANALYTICS_REQUEST_VOCABULARY,
)

_MAX_FALLBACK_TITLE_CHARS = 60

_TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

_FILLER_WORDS = _STOPWORDS | ANALYTICS_REQUEST_VOCABULARY

_LEADING_PHRASES = tuple(
    sorted(
        (
            "tell me ",
            "can you ",
            "how many ",
            "what is the ",
            "what is ",
            "what are the ",
            "what are ",
            "please ",
            "give me ",
        ),
        key=len,
        reverse=True,
    )
)


def derive_response_title(question: str) -> str:
    """Derive a short human-readable title from the user's question."""
    stripped = question.strip()
    if not stripped:
        return _fallback_title(stripped)

    normalized = apply_synonyms(stripped)
    working = _strip_leading_phrases(normalized)
    tokens = _TOKEN_PATTERN.findall(working)
    kept = [token for token in tokens if token.lower() not in _FILLER_WORDS]

    if kept:
        return _join_title_case(kept)

    return _fallback_title(stripped)


def _strip_leading_phrases(text: str) -> str:
    working = text.strip()
    while working:
        lower = working.lower()
        matched = False
        for phrase in _LEADING_PHRASES:
            if lower.startswith(phrase):
                working = working[len(phrase) :].lstrip()
                matched = True
                break
        if not matched:
            break
    return working


def _join_title_case(tokens: list[str]) -> str:
    return " ".join(token[:1].upper() + token[1:].lower() if token else "" for token in tokens)


def _fallback_title(question: str) -> str:
    fallback = _join_title_case(_TOKEN_PATTERN.findall(question))
    if not fallback:
        return "Question"
    if len(fallback) <= _MAX_FALLBACK_TITLE_CHARS:
        return fallback
    truncated = fallback[:_MAX_FALLBACK_TITLE_CHARS].rsplit(" ", 1)[0]
    return truncated or fallback[:_MAX_FALLBACK_TITLE_CHARS]
