from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from talk_to_data_slackbot.pandas_ai.semantic_loader import (
    ColumnDefinition,
    SemanticModelDefinition,
    SemanticModelsLoadResult,
    load_semantic_models,
)

_MULTIWORD_CONNECTORS = re.compile(r"[\s_\-]+")
_BULLET_LINE = re.compile(r"^\s*-\s+(.+?)\s*$", re.MULTILINE)
_INLINE_DASH_SEGMENT = re.compile(r"\s+-\s+")


@dataclass(frozen=True)
class ConceptLexicon:
    """Normalized business terms and phrases derived from semantic models."""

    terms: frozenset[str]
    phrases: tuple[str, ...]


def build_concept_lexicon(
    models: SemanticModelsLoadResult | list[SemanticModelDefinition],
) -> ConceptLexicon:
    """Build a deterministic lexicon from loaded semantic model definitions."""
    model_list = (
        models.models if isinstance(models, SemanticModelsLoadResult) else models
    )

    terms: set[str] = set()
    phrases: set[str] = set()

    for model in model_list:
        _add_term(terms, phrases, model.name)

        for line in _extract_description_phrases(model.description):
            _add_phrase(terms, phrases, line)

        for column in model.columns:
            _add_column_terms(terms, phrases, column)
            for line in _extract_description_phrases(column.description):
                _add_phrase(terms, phrases, line)

        for relationship in model.relationships:
            _add_term(terms, phrases, relationship.from_column)
            _add_term(terms, phrases, relationship.to.dataset)
            _add_term(terms, phrases, relationship.to.column)

    phrase_list = tuple(sorted(phrases, key=lambda item: (-len(item), item)))
    return ConceptLexicon(terms=frozenset(terms), phrases=phrase_list)


@lru_cache(maxsize=1)
def get_default_concept_lexicon() -> ConceptLexicon:
    """Cached lexicon built from the repository ``semantic_models/`` directory."""
    return build_concept_lexicon(load_semantic_models())


def clear_lexicon_cache() -> None:
    """Clear cached lexicon (for tests)."""
    get_default_concept_lexicon.cache_clear()


def _add_column_terms(
    terms: set[str],
    phrases: set[str],
    column: ColumnDefinition,
) -> None:
    _add_term(terms, phrases, column.name)
    if column.alias:
        _add_term(terms, phrases, column.alias)

    for token in _typical_values(column.description):
        _add_term(terms, phrases, token)

    if column.expression:
        _add_phrase(terms, phrases, column.name.replace("_", " "))


def _add_term(terms: set[str], phrases: set[str], raw: str) -> None:
    normalized = _normalize_text(raw)
    if not normalized:
        return
    terms.add(normalized)
    if " " in normalized:
        phrases.add(normalized)


def _add_phrase(terms: set[str], phrases: set[str], raw: str) -> None:
    normalized = _normalize_text(raw)
    if not normalized:
        return
    phrases.add(normalized)
    for token in _MULTIWORD_CONNECTORS.split(normalized):
        if len(token) >= 2:
            terms.add(token)


def _normalize_text(text: str) -> str:
    cleaned = re.sub(r"[^\w\s\-]", " ", text.lower())
    cleaned = _MULTIWORD_CONNECTORS.sub(" ", cleaned)
    return " ".join(cleaned.split())


def _extract_description_phrases(description: str) -> list[str]:
    """Extract business phrases from newline bullets and folded inline `` - `` lists."""
    phrases: list[str] = []
    for match in _BULLET_LINE.finditer(description):
        phrases.extend(_phrase_candidates(match.group(1).strip()))

    for segment in _INLINE_DASH_SEGMENT.split(description):
        segment = segment.strip()
        if not segment:
            continue
        phrases.extend(_phrase_candidates(segment))

    for keyword in _PROSE_BUSINESS_KEYWORDS.finditer(description):
        phrases.append(keyword.group(1))

    return phrases


_PROSE_BUSINESS_KEYWORDS = re.compile(
    r"\b("
    r"churn|retention|engagement|revenue|subscriptions?|sessions?|"
    r"payments?|signup|expiration"
    r")\b",
    re.IGNORECASE,
)


def _phrase_candidates(raw_segment: str) -> list[str]:
    if not raw_segment:
        return []

    candidates: list[str] = []
    segment = raw_segment.strip()

    if ":" in segment:
        label, remainder = segment.split(":", 1)
        label = label.strip()
        remainder = remainder.strip()
        if _looks_like_section_header(label):
            if remainder:
                segment = remainder
        else:
            candidates.append(label)
            if remainder and "status=" not in remainder:
                candidates.append(remainder)
            return candidates

    if "status=" in segment or " via " in segment.lower():
        segment = segment.split(":", 1)[0].strip()

    if segment:
        candidates.append(segment)
    return candidates


def _looks_like_section_header(label: str) -> bool:
    lowered = label.lower()
    return lowered.endswith(
        (
            "semantics",
            "definitions",
            "questions",
            "rules",
        )
    ) or "business rules" in lowered


def _typical_values(description: str) -> list[str]:
    """Extract enumerated values from 'Typical values:' / 'Valid values:' sections."""
    values: list[str] = []
    capture = False
    for line in description.splitlines():
        stripped = line.strip()
        lower = stripped.lower()
        if lower.startswith("typical values:") or lower.startswith("valid values:"):
            capture = True
            continue
        if capture:
            if stripped.startswith("- "):
                values.append(stripped[2:].strip())
            elif stripped and not stripped.startswith("-"):
                capture = False
    return values
