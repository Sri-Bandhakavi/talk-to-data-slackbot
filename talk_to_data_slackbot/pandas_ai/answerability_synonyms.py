from __future__ import annotations

import re

# Maintainer-approved guardrail-only paraphrases (not semantic-model aliases).
# Cap enforced in tests; prefer promoting stable terms to semantic_models alias fields.
MAX_SYNONYM_ENTRIES = 10

QUESTION_TERM_SYNONYMS: dict[str, str] = {
    "customer": "user",
    "geography": "region",
    "device": "platform",
}


def apply_synonyms(text: str) -> str:
    """Replace approved question terms with lexicon terms (whole-token, case-insensitive)."""
    if not text.strip():
        return text

    def replace_token(match: re.Match[str]) -> str:
        token = match.group(0)
        lower = token.lower()
        is_plural = lower.endswith("s") and len(lower) > 3
        singular = lower[:-1] if is_plural else lower
        replacement = QUESTION_TERM_SYNONYMS.get(singular)
        if replacement is None:
            return token
        if is_plural:
            replacement = f"{replacement}s"
        return _preserve_token_case(token, replacement)

    return re.sub(r"[A-Za-z_][A-Za-z0-9_]*", replace_token, text)


def _preserve_token_case(token: str, replacement: str) -> str:
    if token.isupper():
        return replacement.upper()
    if token[0].isupper():
        return replacement.capitalize()
    return replacement
